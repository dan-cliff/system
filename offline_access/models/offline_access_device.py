import hashlib
import logging
import re
import time
from datetime import timedelta

from odoo import api, fields, models
from odoo.http import STORED_SESSION_BYTES, request, root
from odoo.tools import file_open, str2bool

DEFAULT_THEME_COLOR = '#714B67'
DEFAULT_HEARTBEAT_MINUTES = 15
DEFAULT_STALE_DAYS = 14
DEFAULT_MAX_OFFLINE_DAYS = 14
DEFAULT_LOG_DAYS = 30
DEVICE_UID_RE = re.compile(r'^[A-Za-z0-9-]{16,64}$')
_logger = logging.getLogger(__name__)
# Odoo's service worker is extended by: a prelude that runs before Odoo's own
# code, and the main part (with the offline data logic inserted) after it.
SERVICE_WORKER_PRELUDE = 'offline_access/static/src/sw/prelude.js'
SERVICE_WORKER_MAIN = 'offline_access/static/src/sw/service_worker.js'
SERVICE_WORKER_OFFLINE_RPC = 'offline_access/static/src/sw/offline_rpc.js'


def _positive_int(value, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


class OfflineAccessDevice(models.Model):
    _name = 'offline.access.device'
    _description = 'Offline Access Device'
    _order = 'last_seen desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    device_uid = fields.Char(string='Device ID', required=True, readonly=True, index=True,
                             help='Random ID the browser keeps for itself, so its reports can be matched up.')
    user_id = fields.Many2one('res.users', string='User', required=True, readonly=True,
                              index=True, ondelete='cascade')
    browser = fields.Char(readonly=True)
    platform = fields.Char(string='Operating System', readonly=True)
    user_agent = fields.Char(readonly=True)
    installed = fields.Boolean(string='Installed as App', readonly=True,
                               help='Opened as an installed app rather than in a browser tab.')
    app_version = fields.Char(readonly=True, help='Version of the offline app files the device last loaded.')
    storage_used_mb = fields.Float(string='Storage Used (MB)', digits=(16, 1), readonly=True)
    storage_quota_mb = fields.Float(string='Storage Available (MB)', digits=(16, 1), readonly=True)
    first_seen = fields.Datetime(readonly=True, default=fields.Datetime.now)
    last_seen = fields.Datetime(readonly=True, default=fields.Datetime.now)
    session_identifier = fields.Char(readonly=True, groups='base.group_system',
                                     help='The login session the device last reported from, ended on Revoke.')
    # Technical state the heartbeat and Revoke rely on, so a fixed selection.
    state = fields.Selection([
        ('active', 'Active'),
        ('stale', 'Stale'),
        ('revoked', 'Revoked'),
    ], default='active', required=True, readonly=True, index=True)
    revoked_at = fields.Datetime(string='Revoked On', readonly=True)
    revoked_by_id = fields.Many2one('res.users', string='Revoked By', readonly=True)
    wipe_sent_at = fields.Datetime(string='Wipe Sent On', readonly=True,
                                   help='When the device was told to wipe the data stored in its browser.')
    last_sync = fields.Datetime(string='Last Sync', readonly=True,
                                help='When the device last downloaded records for offline use.')
    offline_record_count = fields.Integer(string='Records Offline', readonly=True,
                                          help='Records the device kept for offline use at its last sync.')
    sync_log_ids = fields.One2many('offline.access.sync.log', 'device_id', string='Sync Log')
    sync_log_count = fields.Integer(compute='_compute_sync_log_count')

    _device_user_uniq = models.Constraint(
        'UNIQUE(device_uid, user_id)',
        'A device can only be registered once per user.',
    )

    @api.depends('browser', 'platform')
    def _compute_name(self):
        for device in self:
            if device.browser and device.platform:
                device.name = self.env._('%(browser)s on %(platform)s',
                                         browser=device.browser, platform=device.platform)
            else:
                device.name = device.browser or device.platform or self.env._('Unknown device')

    def _compute_sync_log_count(self):
        counts = dict(self.env['offline.access.sync.log']._read_group(
            [('device_id', 'in', self.ids)], ['device_id'], ['__count']))
        for device in self:
            device.sync_log_count = counts.get(device, 0)

    def action_view_sync_log(self):
        action = self.env['ir.actions.act_window']._for_xml_id('offline_access.action_offline_access_sync_log')
        action['domain'] = [('device_id', 'in', self.ids)]
        action['context'] = {}
        return action

    # ── Configuration ────────────────────────────────────────────────────────

    @api.model
    def _get_offline_access_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        theme_color = ICP.get_param('offline_access.theme_color') or ''
        if not re.match(r'^#[0-9a-fA-F]{6}$', theme_color):
            theme_color = DEFAULT_THEME_COLOR
        icon = self.env['ir.attachment'].sudo().browse(
            _positive_int(ICP.get_param('offline_access.icon_attachment_id'), 0)).exists()
        return {
            'enabled': str2bool(ICP.get_param('offline_access.enabled') or 'False'),
            'theme_color': theme_color,
            'heartbeat_minutes': _positive_int(ICP.get_param('offline_access.heartbeat_minutes'),
                                               DEFAULT_HEARTBEAT_MINUTES),
            'stale_days': _positive_int(ICP.get_param('offline_access.stale_days'), DEFAULT_STALE_DAYS),
            'max_offline_days': _positive_int(ICP.get_param('offline_access.max_offline_days'),
                                              DEFAULT_MAX_OFFLINE_DAYS),
            'log_days': _positive_int(ICP.get_param('offline_access.log_days'), DEFAULT_LOG_DAYS),
            'icon': icon,
            'icon_version': (icon.checksum or str(icon.id))[:12] if icon else False,
        }

    @api.model
    def _get_service_worker_extension(self):
        """The scripts that extend Odoo's service worker: (prelude, main part,
        version). The prelude goes before Odoo's own code, the main part after.

        The version is a hash of the scripts, so browsers pick up a new service
        worker (and drop old cached files) whenever they change."""
        with file_open(SERVICE_WORKER_PRELUDE) as f:
            prelude = f.read()
        with file_open(SERVICE_WORKER_MAIN) as f:
            main = f.read()
        with file_open(SERVICE_WORKER_OFFLINE_RPC) as f:
            offline_rpc = f.read()
        main = main.replace('/* __OFFLINE_ACCESS_RPC__ */', offline_rpc)
        version = hashlib.sha256((prelude + main).encode()).hexdigest()[:12]
        return prelude, main.replace('__OFFLINE_ACCESS_VERSION__', version), version

    # ── Reports from the browser ─────────────────────────────────────────────

    @api.model
    def _valid_device_uid(self, device_uid):
        return isinstance(device_uid, str) and bool(DEVICE_UID_RE.match(device_uid))

    @api.model
    def _register_heartbeat(self, user, device_uid, info):
        """Record a report from ``user``'s browser ``device_uid``. Returns what
        the browser should do next."""
        # Revoke applies to the browser, whoever is signed in to it now.
        if self._check_wipe(device_uid)['wipe']:
            return {'wipe': True}
        now = fields.Datetime.now()
        device = self.search([('device_uid', '=', device_uid), ('user_id', '=', user.id)], limit=1)
        values = {
            'browser': (info.get('browser') or '')[:64] or False,
            'platform': (info.get('platform') or '')[:64] or False,
            'user_agent': (info.get('user_agent') or '')[:512] or False,
            'installed': bool(info.get('installed')),
            'app_version': (info.get('app_version') or '')[:32] or False,
            'storage_used_mb': self._to_mb(info.get('storage_used')),
            'storage_quota_mb': self._to_mb(info.get('storage_quota')),
            'last_seen': now,
            'state': 'active',
        }
        if request and request.session.sid:
            values['session_identifier'] = request.session.sid[:STORED_SESSION_BYTES]
        if device:
            device.write(values)
        else:
            device = self.create(dict(values, device_uid=device_uid, user_id=user.id, first_seen=now))
        return {'wipe': False}

    @api.model
    def _sync(self, user, device_uid, cursors):
        """Records for ``user``'s device to keep offline, read as that user so
        their access rights and record rules apply. ``cursors`` is what the
        device kept from its last sync, per Offline Model id."""
        started = time.monotonic()
        device = self.search([('device_uid', '=', device_uid), ('user_id', '=', user.id)], limit=1)
        Log = self.env['offline.access.sync.log']
        log_values = {'device_id': device.id, 'user_id': user.id}
        try:
            payloads = []
            for offline_model in self.env['offline.access.model'].with_user(user).search([]):
                if offline_model.model_name not in self.env:
                    continue
                payload = offline_model._sync_payload((cursors or {}).get(str(offline_model.id)))
                if payload:
                    payloads.append(payload)
        except Exception as e:  # noqa: BLE001 - logged for the administrator, reported to the device
            _logger.exception("Offline Access: sync failed for user %s", user.id)
            self.env.cr.rollback()
            self.env.invalidate_all()
            Log.create(dict(log_values, state='error', error=str(e)[:2000],
                            duration=time.monotonic() - started))
            return {'error': str(e)}
        records_kept = sum(len(p['ids']) for p in payloads)
        if device:
            device.write({'last_sync': fields.Datetime.now(), 'offline_record_count': records_kept})
        Log.create(dict(
            log_values,
            duration=time.monotonic() - started,
            model_count=len(payloads),
            records_sent=sum(len(p['records']) for p in payloads),
            records_kept=records_kept,
        ))
        config = self._get_offline_access_config()
        return {
            'server_time': fields.Datetime.to_string(fields.Datetime.now()),
            'max_offline_days': config['max_offline_days'],
            'models': payloads,
        }

    @api.model
    def _check_wipe(self, device_uid):
        """For a browser that may no longer be signed in: should it wipe its data?"""
        devices = self.search([('device_uid', '=', device_uid), ('state', '=', 'revoked')])
        if not devices:
            return {'wipe': False}
        devices.filtered(lambda d: not d.wipe_sent_at).wipe_sent_at = fields.Datetime.now()
        return {'wipe': True}

    @api.model
    def _to_mb(self, value):
        try:
            return round(max(float(value or 0), 0) / (1024 * 1024), 1)
        except (TypeError, ValueError):
            return 0

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_revoke(self):
        """Sign the device out now, and wipe its stored data when it next connects."""
        devices = self.filtered(lambda d: d.state != 'revoked')
        if not devices:
            return
        devices.write({
            'state': 'revoked',
            'revoked_at': fields.Datetime.now(),
            'revoked_by_id': self.env.user.id,
            'wipe_sent_at': False,
        })
        identifiers = [i for i in devices.sudo().mapped('session_identifier') if i]
        if identifiers:
            # As Odoo's own "Log out" on a user's devices does.
            root.session_store.delete_from_identifiers(identifiers)
            self.env['res.device.log'].sudo().search([
                ('session_identifier', 'in', identifiers),
            ]).write({'revoked': True})

    def action_cancel_revoke(self):
        """Undo a Revoke that hasn't reached the device yet (it is still signed out)."""
        self.filtered(lambda d: d.state == 'revoked' and not d.wipe_sent_at).write({
            'state': 'active',
            'revoked_at': False,
            'revoked_by_id': False,
        })

    @api.model
    def _cron_mark_stale(self):
        stale_days = self._get_offline_access_config()['stale_days']
        self.search([
            ('state', '=', 'active'),
            ('last_seen', '<', fields.Datetime.now() - timedelta(days=stale_days)),
        ]).write({'state': 'stale'})

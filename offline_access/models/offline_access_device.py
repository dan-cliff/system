import hashlib
import re
from datetime import timedelta

from odoo import api, fields, models
from odoo.http import STORED_SESSION_BYTES, request, root
from odoo.tools import file_open, str2bool

DEFAULT_THEME_COLOR = '#714B67'
DEFAULT_HEARTBEAT_MINUTES = 15
DEFAULT_STALE_DAYS = 14
DEVICE_UID_RE = re.compile(r'^[A-Za-z0-9-]{16,64}$')
SERVICE_WORKER_FILE = 'offline_access/static/src/service_worker.js'


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
            'icon': icon,
            'icon_version': (icon.checksum or str(icon.id))[:12] if icon else False,
        }

    @api.model
    def _get_service_worker_extension(self):
        """The script appended to Odoo's service worker, with its version filled in.

        The version is a hash of the script, so browsers pick up a new service
        worker (and drop old cached files) whenever this module's script changes."""
        with file_open(SERVICE_WORKER_FILE) as f:
            script = f.read()
        version = hashlib.sha256(script.encode()).hexdigest()[:12]
        return script.replace('__OFFLINE_ACCESS_VERSION__', version), version

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

# -*- coding: utf-8 -*-
import hashlib
import logging
import secrets
import shlex
import uuid
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..lib import iot_auth

_logger = logging.getLogger(__name__)

PAIRING_CODE_VALID = timedelta(hours=24)
PAIRING_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
# A Node that hasn't been heard from for this long is shown as offline.
NODE_OFFLINE_AFTER = timedelta(minutes=2)
# How often "last seen" is written (Nodes check in far more often).
NODE_HEARTBEAT_EVERY = timedelta(seconds=30)


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


class IotNode(models.Model):
    """A Node: a Raspberry Pi on our own network that connects Odoo to
    hardware Odoo can't reach itself (Odoo is hosted outside the network).

    The Node runs one program, its Role (e.g. an Embroidery Bridge). It is
    paired once with a one-time code, then signs every request with its own
    rolling key (see lib/iot_auth.py). Apps add their Role and the Role's
    settings to this model.
    """
    _name = 'iot.node'
    _description = 'IoT Node'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True, help='e.g. "Workshop Bridge" or "Workshop TV".')
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company,
                                 tracking=True)
    color = fields.Integer(string='Colour Index')
    # Technical: each Role is a program in code. Apps add theirs with selection_add.
    role = fields.Selection(
        [('custom', 'Custom Program')], required=True, default='custom', tracking=True,
        help='The program this Node runs. Custom Program is for your own scripts using iot_auth.py.',
    )
    location_note = fields.Char(string='Located', help='Where the Node is, e.g. "Under the embroidery bench".')
    note = fields.Html(string='Notes')

    # ── Connection ────────────────────────────────────────────────────────
    last_seen = fields.Datetime(readonly=True, copy=False)
    last_ip = fields.Char(string='Last Address', readonly=True, copy=False,
                          help='Public address the Node last connected from.')
    agent_version = fields.Char(string='Program Version', readonly=True, copy=False)
    is_online = fields.Boolean(string='Online', compute='_compute_is_online')

    # ── Program and over-the-air updates ──────────────────────────────────
    program_id = fields.Many2one('iot.program', compute='_compute_program_id', string='Program')
    # Technical: the update flow depends on these.
    update_policy = fields.Selection(
        [('current', "Always the program's current version"), ('pinned', 'Stay on a chosen version')],
        string='Updates', default='current', required=True, tracking=True,
        help="Over-the-air updates: the Node downloads the version it should run when it next checks in "
             "(within a minute).",
    )
    pinned_version_id = fields.Many2one('iot.program.version', string='Chosen Version', tracking=True,
                                        domain="[('role', '=', role), ('state', '=', 'released')]")
    target_version_id = fields.Many2one('iot.program.version', compute='_compute_update_state',
                                        string='Should Run')
    installed_version_id = fields.Many2one('iot.program.version', string='Running', readonly=True, copy=False)
    installed_digest = fields.Char(readonly=True, copy=False)
    installed_on = fields.Datetime(string='Updated On', readonly=True, copy=False)
    update_state = fields.Selection(
        [('none', 'No Program'), ('current', 'Up to Date'), ('pending', 'Update Waiting'), ('failed', 'Update Failed')],
        compute='_compute_update_state', string='Update Status',
    )
    update_error = fields.Text(string='Update Problem', readonly=True, copy=False)
    setup_changed = fields.Boolean(
        string='Setup Changed', readonly=True, copy=False,
        help='The running version changes what the install command sets up (as root), which updates over the '
             'air never do: run the install command on the Node again to apply it.',
    )

    # ── Security ──────────────────────────────────────────────────────────
    node_key = fields.Char(string='Node ID', readonly=True, copy=False, index=True,
                           default=lambda self: uuid.uuid4().hex)
    auth_secret = fields.Char(copy=False, groups='base.group_system')
    auth_secret_next = fields.Char(copy=False, groups='base.group_system')
    auth_last_ts = fields.Float(copy=False, groups='base.group_system', digits=(16, 0))
    pairing_code_hash = fields.Char(copy=False, groups='base.group_system')
    pairing_expires = fields.Datetime(string='Pairing Code Expires', readonly=True, copy=False)
    is_paired = fields.Boolean(string='Paired', compute='_compute_is_paired', compute_sudo=True)
    paired_on = fields.Datetime(readonly=True, copy=False)
    paired_hostname = fields.Char(string='Host Name', readonly=True, copy=False,
                                  help='Host name the Node reported when it paired.')
    key_rotated_on = fields.Datetime(string='Key Last Changed', readonly=True, copy=False)
    key_rotate_days = fields.Integer(
        string='Change Key Every (days)', default=30,
        help='Odoo gives the Node a new secret key this often, without re-pairing. 0 keeps the same key.',
    )
    allowed_macs = fields.Text(
        string='Authorised MAC Addresses', copy=False, tracking=True,
        help='Only a Node with one of these network addresses (one per line, e.g. b8:27:eb:12:34:56) '
             'is let in. Leave empty to allow any.',
    )
    authorise_paired_mac = fields.Boolean(
        string='Authorise the Node That Pairs', default=True,
        help='When the Authorised MAC Addresses list is empty, add the address of the Node that pairs, '
             'so only that Node can use the key.',
    )
    last_mac = fields.Char(string='Last MAC Address', readonly=True, copy=False)
    last_auth_error = fields.Char(string='Last Refused Request', readonly=True, copy=False)
    last_auth_error_on = fields.Datetime(string='Refused On', readonly=True, copy=False)

    _node_key_unique = models.Constraint('UNIQUE(node_key)', 'Each Node needs its own Node ID.')

    @api.depends('last_seen')
    def _compute_is_online(self):
        limit = fields.Datetime.now() - NODE_OFFLINE_AFTER
        for node in self:
            node.is_online = bool(node.last_seen and node.last_seen >= limit)

    @api.depends('auth_secret')
    def _compute_is_paired(self):
        for node in self:
            node.is_paired = bool(node.auth_secret)

    @api.depends('role')
    def _compute_program_id(self):
        programs = {p.role: p for p in self.env['iot.program'].search([('role', 'in', self.mapped('role'))])}
        for node in self:
            node.program_id = programs.get(node.role, self.env['iot.program'])

    @api.depends('role', 'update_policy', 'pinned_version_id', 'installed_version_id', 'installed_digest',
                 'update_error')
    def _compute_update_state(self):
        for node in self:
            target = node._iot_target_version()
            node.target_version_id = target
            if not target:
                node.update_state = 'none'
            elif node.installed_digest == target.digest:
                node.update_state = 'current'
            elif node.update_error:
                node.update_state = 'failed'
            else:
                node.update_state = 'pending'

    def _iot_target_version(self):
        self.ensure_one()
        if self.update_policy == 'pinned' and self.pinned_version_id:
            return self.pinned_version_id
        return self.program_id.current_version_id

    @api.model
    def _normalise_allowed_macs(self, vals):
        if vals.get('allowed_macs'):
            valid, invalid = iot_auth.parse_macs(vals['allowed_macs'])
            if invalid:
                raise ValidationError(_('These are not MAC addresses: %s. Write them like b8:27:eb:12:34:56.',
                                        ', '.join(invalid)))
            vals['allowed_macs'] = '\n'.join(sorted(valid))
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._normalise_allowed_macs(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._normalise_allowed_macs(vals)
        if 'role' in vals and any(node.is_paired and node.role != vals['role'] for node in self):
            raise UserError(_("A paired Node's role can't be changed: revoke its access first, "
                              "then pair it again with the new program."))
        return super().write(vals)

    # ── Hooks for the apps that add Roles ─────────────────────────────────
    def _iot_hello_data(self):
        """Extra values the Node's check-in answer carries for its role."""
        self.ensure_one()
        return {}

    # ── Pairing ───────────────────────────────────────────────────────────
    def _install_command(self, code):
        """The one command that builds any Node: the agent, pairing, and the
        role's program, which the agent then keeps up to date over the air."""
        self.ensure_one()
        base = self.get_base_url().rstrip('/')
        return 'curl -fsSL %s/iot/install.sh | sudo bash -s -- --url %s --pair %s' % (
            shlex.quote(base), shlex.quote(base), shlex.quote(code))

    def action_pair(self):
        """Make a one-time pairing code and show the install command."""
        self.ensure_one()
        code = '-'.join(''.join(secrets.choice(PAIRING_ALPHABET) for _i in range(4)) for _j in range(4))
        expires = fields.Datetime.now() + PAIRING_CODE_VALID
        self.sudo().write({'pairing_code_hash': _hash(code), 'pairing_expires': expires})
        self.message_post(body=_('Pairing code made by %s (valid until it is used or 24 hours).',
                                 self.env.user.name))
        wizard = self.env['iot.node.pair.wizard'].create({
            'node_id': self.id,
            'code': code,
            'expires': expires,
            'install_command': self._install_command(code),
            'already_paired': self.is_paired,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pair a Node'),
            'res_model': 'iot.node.pair.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_revoke(self):
        """Lock the Node out: it has to be paired again."""
        self.sudo().write({
            'auth_secret': False,
            'auth_secret_next': False,
            'pairing_code_hash': False,
            'pairing_expires': False,
            'paired_on': False,
        })
        for node in self:
            node.message_post(body=_('Access revoked by %s.', self.env.user.name))
        return True

    @api.model
    def _iot_pair(self, code, role, mac, macs, hostname):
        """Pair the Node holding ``code``: returns (node, secret) or raises UserError."""
        node = self.sudo().search([('pairing_code_hash', '=', _hash((code or '').strip().upper()))], limit=1)
        if not node or not node.pairing_expires or node.pairing_expires < fields.Datetime.now():
            raise UserError(_('This pairing code is wrong or has expired. Make a new one in Odoo.'))
        if role and role != node.role:
            roles = dict(node._fields['role']._description_selection(node.env))
            raise UserError(_('This pairing code is for a %(expected)s Node, not a %(given)s.',
                              expected=roles.get(node.role, node.role), given=roles.get(role, role)))
        mac = iot_auth.normalise_mac(mac)
        reported = {m for m in (iot_auth.normalise_mac(m) for m in (macs or [])) if m} | ({mac} if mac else set())
        allowed, _invalid = iot_auth.parse_macs(node.allowed_macs)
        if allowed and not reported & allowed:
            _logger.warning('IoT Node %s (%s): pairing refused from %s', node.id, node.name, mac)
            raise UserError(_('This Node (%s) is not one of the authorised MAC addresses.', mac or '?'))
        vals = {
            'auth_secret': secrets.token_urlsafe(32),
            'auth_secret_next': False,
            'auth_last_ts': 0,
            'pairing_code_hash': False,
            'pairing_expires': False,
            'paired_on': fields.Datetime.now(),
            'paired_hostname': (hostname or '')[:64] or False,
            'key_rotated_on': fields.Datetime.now(),
            'last_mac': mac or False,
        }
        if not allowed and node.authorise_paired_mac and mac:
            vals['allowed_macs'] = mac
        node.write(vals)
        node.message_post(body=_('Paired from %(host)s (%(mac)s).', host=hostname or '?', mac=mac or '?'))
        return node, vals['auth_secret']

    # ── Checking requests ─────────────────────────────────────────────────
    def _iot_refused(self, reason, mac=None):
        self.ensure_one()
        _logger.warning('IoT Node %s (%s): request refused: %s', self.id, self.name, reason)
        self.sudo().write({
            'last_auth_error': reason[:250],
            'last_auth_error_on': fields.Datetime.now(),
            'last_mac': mac or self.last_mac,
        })

    @api.model
    def _iot_authenticate(self, httprequest, roles=None):
        """Check a signed request. Returns (node as sudo, None) or (None, reason).

        ``roles``: the roles allowed to call this endpoint (None for any).
        """
        headers = httprequest.headers
        key = headers.get(iot_auth.HEADER_NODE, '')
        signature = headers.get(iot_auth.HEADER_SIGNATURE, '')
        mac = iot_auth.normalise_mac(headers.get(iot_auth.HEADER_MAC, ''))
        try:
            timestamp = int(headers.get(iot_auth.HEADER_TIMESTAMP, ''))
        except ValueError:
            timestamp = None
        if not key or not signature or timestamp is None:
            return None, 'This request is not signed.'
        node = self.sudo().search([('node_key', '=', key)], limit=1)
        if not node:
            return None, 'Unknown Node.'
        if not node.auth_secret:
            node._iot_refused(_('The Node is not paired.'), mac)
            return None, 'This Node is not paired. Pair it again from Odoo.'
        if roles and node.role not in roles:
            node._iot_refused(_('Its role may not use %s.', httprequest.path), mac)
            return None, "This Node's role can't use this service."
        now_ms = int(fields.Datetime.now().timestamp() * 1000)
        if abs(now_ms - timestamp) > iot_auth.MAX_CLOCK_SKEW_MS:
            node._iot_refused(_("The Node's clock is wrong by %s seconds.", round((timestamp - now_ms) / 1000)), mac)
            return None, "The Node's clock is wrong. Check its date and time."
        allowed, _invalid = iot_auth.parse_macs(node.allowed_macs)
        if allowed and mac not in allowed:
            node._iot_refused(_('%s is not an authorised MAC address.', mac or 'No MAC address'), mac)
            return None, 'This Node is not authorised.'
        path = httprequest.path + ('?' + httprequest.query_string.decode('latin-1') if httprequest.query_string else '')
        body = httprequest.get_data(cache=True)
        args = (signature, httprequest.method, path, timestamp, mac, key, body)
        if iot_auth.verify(node.auth_secret, *args):
            used_next = False
        elif node.auth_secret_next and iot_auth.verify(node.auth_secret_next, *args):
            used_next = True
        else:
            node._iot_refused(_('Wrong signature.'), mac)
            return None, 'The request signature is wrong. Pair the Node again.'
        # Each timestamp may only be used once, and they must increase.
        self.env.cr.execute(
            'UPDATE "%s" SET auth_last_ts = %%s WHERE id = %%s AND COALESCE(auth_last_ts, 0) < %%s RETURNING id'
            % node._table, [timestamp, node.id, timestamp],
        )
        if not self.env.cr.fetchone():
            node._iot_refused(_('Replayed or out-of-order request.'), mac)
            return None, 'This request was already used.'
        node.invalidate_recordset(['auth_last_ts'])
        vals = {}
        if used_next:
            # The Node has the new key: the old one stops working.
            vals.update(auth_secret=node.auth_secret_next, auth_secret_next=False,
                        key_rotated_on=fields.Datetime.now())
        if mac and mac != node.last_mac:
            vals['last_mac'] = mac
        if vals:
            node.write(vals)
        return node, None

    def _iot_new_secret(self):
        """A new key to hand to the Node in a signed response, if it is time for one."""
        self.ensure_one()
        node = self.sudo()
        if not node.auth_secret_next and node.key_rotate_days > 0 and (
            not node.key_rotated_on
            or node.key_rotated_on <= fields.Datetime.now() - timedelta(days=node.key_rotate_days)
        ):
            node.auth_secret_next = secrets.token_urlsafe(32)
        return node.auth_secret_next or None

    # ── Over-the-air updates ──────────────────────────────────────────────
    def _iot_program_payload(self):
        """What the Node should run, for its check-in answer (None: no program)."""
        self.ensure_one()
        version = self._iot_target_version()
        if not version:
            return None
        return {
            'version_id': version.id,
            'name': version.name,
            'digest': version.digest,
            'entrypoint': version.entrypoint or '',
            'home': version.home_path or '',
            'setup': version.setup_script or '',
            'setup_sha256': version.file_ids.filtered(lambda f: f.path == version.setup_script).sha256 or '',
            'files': [{'id': f.id, 'path': f.path, 'sha256': f.sha256, 'size': f.size,
                       'url': '/iot/v1/program/file/%s' % f.id} for f in version.file_ids],
        }

    def _iot_report_program(self, report):
        """Record what the Node says it runs: {'digest', 'version_id', 'error', 'setup_changed'}."""
        self.ensure_one()
        if not isinstance(report, dict):
            return
        vals = {}
        digest = str(report.get('digest') or '')[:64] or False
        if digest != self.installed_digest:
            version = self.env['iot.program.version'].search(
                [('role', '=', self.role), ('digest', '=', digest)], limit=1) if digest else False
            vals.update(installed_digest=digest, installed_version_id=version.id if version else False,
                        installed_on=fields.Datetime.now())
            if version:
                self.message_post(body=_('Now running %s.', version.name))
        error = str(report.get('error') or '')[:2000] or False
        if error != self.update_error:
            vals['update_error'] = error
            if error:
                self.message_post(body=_('Update failed: %s', error))
        if bool(report.get('setup_changed')) != self.setup_changed:
            vals['setup_changed'] = bool(report.get('setup_changed'))
        if vals:
            self.write(vals)

    def _iot_heartbeat(self, ip=None, version=None):
        """Note that the Node checked in (last seen written at most every 30 s)."""
        self.ensure_one()
        now = fields.Datetime.now()
        vals = {}
        if not self.last_seen or now - self.last_seen >= NODE_HEARTBEAT_EVERY:
            vals['last_seen'] = now
        if ip and ip != self.last_ip:
            vals['last_ip'] = ip
        if version and version != self.agent_version:
            vals['agent_version'] = version[:32]
        if vals:
            self.write(vals)

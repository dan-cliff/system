# -*- coding: utf-8 -*-
import hashlib
import logging
import secrets
import uuid
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..lib import device_auth

_logger = logging.getLogger(__name__)

PAIRING_CODE_VALID = timedelta(hours=24)
PAIRING_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


class EmbroideryDeviceMixin(models.AbstractModel):
    """Pairing and signed-request security for a Raspberry Pi.

    See lib/device_auth.py for how requests are signed.
    """
    _name = 'embroidery.device.mixin'
    _description = 'Raspberry Pi Security'

    # The program the Pi runs: 'bridge' or 'display'.
    _device_kind = None

    device_key = fields.Char(string='Device ID', readonly=True, copy=False, index=True,
                             default=lambda self: uuid.uuid4().hex)
    auth_secret = fields.Char(copy=False, groups='base.group_system')
    auth_secret_next = fields.Char(copy=False, groups='base.group_system')
    auth_last_ts = fields.Float(copy=False, groups='base.group_system', digits=(16, 0))
    pairing_code_hash = fields.Char(copy=False, groups='base.group_system')
    pairing_expires = fields.Datetime(string='Pairing Code Expires', readonly=True, copy=False)
    is_paired = fields.Boolean(string='Paired', compute='_compute_is_paired', compute_sudo=True)
    paired_on = fields.Datetime(readonly=True, copy=False)
    paired_hostname = fields.Char(string='Pi Name', readonly=True, copy=False,
                                  help='Host name the Raspberry Pi reported when it paired.')
    key_rotated_on = fields.Datetime(string='Key Last Changed', readonly=True, copy=False)
    key_rotate_days = fields.Integer(
        string='Change Key Every (days)', default=30,
        help='Odoo gives the Pi a new secret key this often, without re-pairing. 0 keeps the same key.',
    )
    allowed_macs = fields.Text(
        string='Authorised MAC Addresses', copy=False,
        help='Only a Raspberry Pi with one of these network addresses (one per line, e.g. '
             'b8:27:eb:12:34:56) is let in. Leave empty to allow any.',
    )
    authorise_paired_mac = fields.Boolean(
        string='Authorise the Pi That Pairs', default=True,
        help='When the Authorised MAC Addresses list is empty, add the address of the Pi that pairs, '
             'so only that Pi can use the key.',
    )
    last_mac = fields.Char(string='Last MAC Address', readonly=True, copy=False)
    last_auth_error = fields.Char(string='Last Refused Request', readonly=True, copy=False)
    last_auth_error_on = fields.Datetime(string='Refused On', readonly=True, copy=False)

    @api.depends('auth_secret')
    def _compute_is_paired(self):
        for device in self:
            device.is_paired = bool(device.auth_secret)

    @api.model
    def _normalise_allowed_macs(self, vals):
        if vals.get('allowed_macs'):
            valid, invalid = device_auth.parse_macs(vals['allowed_macs'])
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
        return super().write(vals)

    # ── Pairing ───────────────────────────────────────────────────────────
    def _install_command(self, code):
        """The command to run on the Pi to install and pair it."""
        raise NotImplementedError

    def action_pair(self):
        """Make a one-time pairing code and show the install command."""
        self.ensure_one()
        code = '-'.join(''.join(secrets.choice(PAIRING_ALPHABET) for _i in range(4)) for _j in range(4))
        expires = fields.Datetime.now() + PAIRING_CODE_VALID
        self.sudo().write({'pairing_code_hash': _hash(code), 'pairing_expires': expires})
        wizard = self.env['embroidery.device.pair.wizard'].create({
            'name': self.display_name,
            'code': code,
            'expires': expires,
            'install_command': self._install_command(code),
            'already_paired': self.is_paired,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pair a Raspberry Pi'),
            'res_model': 'embroidery.device.pair.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_revoke(self):
        """Lock the Pi out: it has to be paired again."""
        self.sudo().write({
            'auth_secret': False,
            'auth_secret_next': False,
            'pairing_code_hash': False,
            'pairing_expires': False,
            'paired_on': False,
        })
        return True

    @api.model
    def _auth_pair(self, code, mac, macs, hostname):
        """Pair the Pi holding ``code``: returns (device, secret) or raises UserError."""
        device = self.sudo().search([('pairing_code_hash', '=', _hash((code or '').strip().upper()))], limit=1)
        if not device or not device.pairing_expires or device.pairing_expires < fields.Datetime.now():
            raise UserError(_('This pairing code is wrong or has expired. Make a new one in Odoo.'))
        mac = device_auth.normalise_mac(mac)
        reported = {m for m in (device_auth.normalise_mac(m) for m in (macs or [])) if m} | ({mac} if mac else set())
        allowed, _invalid = device_auth.parse_macs(device.allowed_macs)
        if allowed and not reported & allowed:
            device._auth_refused(_('Pairing refused: %s is not an authorised MAC address.', mac or '?'), mac)
            raise UserError(_('This Raspberry Pi (%s) is not one of the authorised MAC addresses.', mac or '?'))
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
        if not allowed and device.authorise_paired_mac and mac:
            vals['allowed_macs'] = mac
        device.write(vals)
        return device, vals['auth_secret']

    # ── Checking requests ─────────────────────────────────────────────────
    def _auth_refused(self, reason, mac=None):
        self.ensure_one()
        _logger.warning('Embroidery %s %s (%s): request refused: %s', self._device_kind, self.id, self.display_name, reason)
        self.sudo().write({
            'last_auth_error': reason[:250],
            'last_auth_error_on': fields.Datetime.now(),
            'last_mac': mac or self.last_mac,
        })

    @api.model
    def _auth_request(self, httprequest):
        """Check a signed request. Returns (device as sudo, None) or (None, reason)."""
        headers = httprequest.headers
        key = headers.get(device_auth.HEADER_DEVICE, '')
        signature = headers.get(device_auth.HEADER_SIGNATURE, '')
        mac = device_auth.normalise_mac(headers.get(device_auth.HEADER_MAC, ''))
        try:
            timestamp = int(headers.get(device_auth.HEADER_TIMESTAMP, ''))
        except ValueError:
            timestamp = None
        if not key or not signature or timestamp is None:
            return None, 'This request is not signed.'
        device = self.sudo().search([('device_key', '=', key)], limit=1)
        if not device:
            return None, 'Unknown device.'
        if not device.auth_secret:
            device._auth_refused(_('The Pi is not paired.'), mac)
            return None, 'This Raspberry Pi is not paired. Pair it again from Odoo.'
        now_ms = int(fields.Datetime.now().timestamp() * 1000)
        if abs(now_ms - timestamp) > device_auth.MAX_CLOCK_SKEW_MS:
            device._auth_refused(_("The Pi's clock is wrong by %s seconds.", round((timestamp - now_ms) / 1000)), mac)
            return None, "The Raspberry Pi's clock is wrong. Check its date and time."
        allowed, _invalid = device_auth.parse_macs(device.allowed_macs)
        if allowed and mac not in allowed:
            device._auth_refused(_('%s is not an authorised MAC address.', mac or 'No MAC address'), mac)
            return None, 'This Raspberry Pi is not authorised.'
        path = httprequest.path + ('?' + httprequest.query_string.decode('latin-1') if httprequest.query_string else '')
        body = httprequest.get_data(cache=True)
        args = (signature, httprequest.method, path, timestamp, mac, key, body)
        if device_auth.verify(device.auth_secret, *args):
            used_next = False
        elif device.auth_secret_next and device_auth.verify(device.auth_secret_next, *args):
            used_next = True
        else:
            device._auth_refused(_('Wrong signature.'), mac)
            return None, 'The request signature is wrong. Pair the Raspberry Pi again.'
        # Each timestamp may only be used once, and they must increase.
        self.env.cr.execute(
            'UPDATE "%s" SET auth_last_ts = %%s WHERE id = %%s AND COALESCE(auth_last_ts, 0) < %%s RETURNING id'
            % device._table, [timestamp, device.id, timestamp],
        )
        if not self.env.cr.fetchone():
            device._auth_refused(_('Replayed or out-of-order request.'), mac)
            return None, 'This request was already used.'
        device.invalidate_recordset(['auth_last_ts'])
        vals = {}
        if used_next:
            # The Pi has the new key: the old one stops working.
            vals.update(auth_secret=device.auth_secret_next, auth_secret_next=False,
                        key_rotated_on=fields.Datetime.now())
        if mac and mac != device.last_mac:
            vals['last_mac'] = mac
        if vals:
            device.write(vals)
        return device, None

    def _auth_new_secret(self):
        """A new key to hand to the Pi in a signed response, if it is time for one."""
        self.ensure_one()
        device = self.sudo()
        if not device.auth_secret_next and device.key_rotate_days > 0 and (
            not device.key_rotated_on
            or device.key_rotated_on <= fields.Datetime.now() - timedelta(days=device.key_rotate_days)
        ):
            device.auth_secret_next = secrets.token_urlsafe(32)
        return device.auth_secret_next or None

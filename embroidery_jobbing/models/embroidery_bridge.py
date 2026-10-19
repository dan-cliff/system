# -*- coding: utf-8 -*-
import hashlib
import secrets
from datetime import timedelta

from odoo import _, api, fields, models

# A bridge that hasn't polled for this long is shown as offline.
BRIDGE_OFFLINE_AFTER = timedelta(minutes=2)


class EmbroideryBridge(models.Model):
    """A PC running the Embroidery Bridge program beside the machines.

    The bridge polls Odoo over HTTPS (so nothing needs opening on the
    workshop's router), downloads the files queued for its machines,
    delivers them and reports the stitch-out progress back.
    """
    _name = 'embroidery.bridge'
    _description = 'Embroidery Bridge'
    _order = 'name'

    name = fields.Char(required=True, help='Where the bridge runs, e.g. "Workshop PC".')
    active = fields.Boolean(default=True)
    token_hash = fields.Char(copy=False, groups='base.group_system')
    token_hint = fields.Char(
        string='Access Token', copy=False, readonly=True,
        help='The end of the access token the bridge uses. Generate a new token to replace it.',
    )
    machine_ids = fields.One2many('embroidery.machine', 'bridge_id', string='Machines')
    last_seen = fields.Datetime(readonly=True, copy=False)
    last_ip = fields.Char(string='Last Address', readonly=True, copy=False)
    bridge_version = fields.Char(readonly=True, copy=False)
    is_online = fields.Boolean(string='Online', compute='_compute_is_online')
    note = fields.Text(string='Notes')

    @api.depends('last_seen')
    def _compute_is_online(self):
        limit = fields.Datetime.now() - BRIDGE_OFFLINE_AFTER
        for bridge in self:
            bridge.is_online = bool(bridge.last_seen and bridge.last_seen >= limit)

    @staticmethod
    def _hash_token(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @api.model
    def _authenticate(self, token):
        """The active bridge a token belongs to (sudo), or an empty recordset."""
        if not token or len(token) < 32:
            return self.sudo().browse()
        return self.sudo().search([('token_hash', '=', self._hash_token(token))], limit=1)

    def action_generate_token(self):
        """Replace the access token and show the new one once."""
        self.ensure_one()
        token = secrets.token_urlsafe(32)
        self.sudo().write({
            'token_hash': self._hash_token(token),
            'token_hint': '…' + token[-6:],
        })
        wizard = self.env['embroidery.bridge.token.wizard'].create({
            'bridge_id': self.id,
            'token': token,
            'odoo_url': self.get_base_url(),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bridge Access Token'),
            'res_model': 'embroidery.bridge.token.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

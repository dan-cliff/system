# -*- coding: utf-8 -*-
import shlex
from datetime import timedelta

from odoo import api, fields, models

# A bridge that hasn't polled for this long is shown as offline.
BRIDGE_OFFLINE_AFTER = timedelta(minutes=2)


class EmbroideryBridge(models.Model):
    """A Raspberry Pi running the Embroidery Bridge program beside the machines.

    The bridge polls Odoo over HTTPS (so nothing needs opening on the
    workshop's router), downloads the files queued for its machines,
    delivers them and reports the stitch-out progress back. Its requests
    are signed with the key it got when it was paired.
    """
    _name = 'embroidery.bridge'
    _description = 'Embroidery Bridge'
    _inherit = ['embroidery.device.mixin']
    _order = 'name'
    _device_kind = 'bridge'

    name = fields.Char(required=True, help='Where the bridge runs, e.g. "Workshop Pi".')
    active = fields.Boolean(default=True)
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

    def _install_command(self, code):
        base = self.get_base_url().rstrip('/')
        return 'curl -fsSL %s/embroidery/bridge/install.sh | sudo bash -s -- --url %s --pair %s' % (
            shlex.quote(base), shlex.quote(base), shlex.quote(code))

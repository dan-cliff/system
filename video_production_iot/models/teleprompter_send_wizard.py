# -*- coding: utf-8 -*-
import uuid
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TeleprompterSendWizard(models.TransientModel):
    _inherit = 'teleprompter.send.wizard'

    delivery = fields.Selection(
        selection_add=[('iot', 'Send to an IoT-connected display')],
        ondelete={'iot': 'set default'},
    )

    # ── IoT fields (only used when delivery == 'iot') ─────────────────────
    iot_box_id = fields.Many2one(
        'iot.box',
        string='IoT Box',
        help='The IoT box your teleprompter display is connected to.',
    )
    display_id = fields.Many2one(
        'iot.device',
        string='Display',
        domain="[('iot_id', '=', iot_box_id), ('type', '=', 'display')]",
        help='The display device to push the teleprompter to.',
    )

    # ── Onchanges ─────────────────────────────────────────────────────────
    @api.onchange('delivery')
    def _onchange_delivery(self):
        self.iot_box_id = False
        self.display_id = False

    @api.onchange('iot_box_id')
    def _onchange_iot_box_id(self):
        self.display_id = False

    # ── Confirm ───────────────────────────────────────────────────────────
    def action_confirm(self):
        self.ensure_one()
        if self.delivery != 'iot':
            return super().action_confirm()

        if not self.iot_box_id:
            raise UserError(_('Please select an IoT box.'))
        if not self.display_id:
            raise UserError(_('Please select a display.'))

        script = self.script_id
        if not script.teleprompter_token:
            script.teleprompter_token = uuid.uuid4().hex

        base_url = script.get_base_url().rstrip('/')
        public_url = '%s/video/teleprompter/%s' % (base_url, script.teleprompter_token)

        # Write display_url — the IoT box polls this and navigates the display
        self.display_id.sudo().write({'display_url': public_url})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Teleprompter sent'),
                'message': _('Now showing on %(box)s › %(display)s') % {
                    'box':     self.iot_box_id.name,
                    'display': self.display_id.name,
                },
                'type': 'success',
                'sticky': False,
            },
        }

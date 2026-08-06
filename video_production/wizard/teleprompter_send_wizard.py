# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TeleprompterSendWizard(models.TransientModel):
    """Choose how to open the teleprompter for an approved script.

    The IoT display option is only added (via `selection_add`) when the
    `video_production_iot` bridge module is installed, so this base wizard
    stays usable when the `iot` app is not present.
    """
    _name = 'teleprompter.send.wizard'
    _description = 'Open Teleprompter'

    # ── Context ───────────────────────────────────────────────────────────
    script_id = fields.Many2one(
        'video.script',
        string='Script',
        required=True,
        readonly=True,
    )
    script_name = fields.Char(
        related='script_id.name',
        string='Script',
        readonly=True,
    )

    # ── Delivery choice ───────────────────────────────────────────────────
    delivery = fields.Selection(
        [
            ('window', 'Open in a new browser window'),
        ],
        string='How to open',
        default='window',
        required=True,
    )

    # ── Confirm ───────────────────────────────────────────────────────────
    def action_confirm(self):
        self.ensure_one()

        if self.delivery == 'window':
            return {
                'type': 'ir.actions.act_url',
                'url': '/video/script/%d/teleprompter' % self.script_id.id,
                'target': 'new',
            }

        raise UserError(_('Unsupported delivery method.'))

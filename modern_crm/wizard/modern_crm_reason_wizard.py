from odoo import fields, models


class ModernCrmReasonWizard(models.TransientModel):
    """Asks why a lead is disqualified or an opportunity is lost."""
    _name = 'modern.crm.reason.wizard'
    _description = 'CRM Disqualify / Lost Reason'

    mode = fields.Selection([('disqualify', 'Disqualify'), ('lost', 'Lost')], required=True)
    lead_ids = fields.Many2many('modern.crm.lead', string='Leads')
    opportunity_ids = fields.Many2many('modern.crm.opportunity', string='Opportunities')
    disqualify_reason_id = fields.Many2one('modern.crm.disqualify.reason', string='Disqualify Reason')
    lost_reason_id = fields.Many2one('modern.crm.lost.reason', string='Lost Reason')
    note = fields.Text('Notes')

    def action_confirm(self):
        self.ensure_one()
        if self.mode == 'disqualify':
            self.lead_ids._check_open()
            self.lead_ids.write({'state': 'disqualified', 'disqualify_reason_id': self.disqualify_reason_id.id,
                                 'disqualify_note': self.note})
        else:
            self.opportunity_ids._action_set_lost(self.lost_reason_id, self.note)
        return {'type': 'ir.actions.act_window_close'}

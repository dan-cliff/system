from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    modern_crm_won_on_order = fields.Boolean(related='company_id.modern_crm_won_on_order', readonly=False)
    modern_crm_web_to_lead = fields.Boolean(related='company_id.modern_crm_web_to_lead', readonly=False)
    modern_crm_web_lead_user_id = fields.Many2one(
        related='company_id.modern_crm_web_lead_user_id', readonly=False)
    modern_crm_web_lead_team_id = fields.Many2one(
        related='company_id.modern_crm_web_lead_team_id', readonly=False)

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    modern_crm_won_on_order = fields.Boolean(
        'Close Won on Sale', default=True,
        help='Mark an opportunity Closed Won when one of its quotes is confirmed.')
    modern_crm_web_to_lead = fields.Boolean(
        'Web-to-Lead Form',
        help='Publish a form at /crm/web-to-lead that creates a lead for each submission.')
    modern_crm_web_lead_user_id = fields.Many2one(
        'res.users', string='Web Lead Owner', domain="[('share', '=', False)]",
        help='Who gets the leads from the Web-to-Lead form. Leave empty to leave them unassigned.')
    modern_crm_web_lead_team_id = fields.Many2one('crm.team', string='Web Lead Sales Team')

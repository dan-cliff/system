from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    modern_crm_contract_template_id = fields.Many2one(
        'modern.crm.contract.template', string='Default Contract Template')
    modern_crm_won_on_order = fields.Boolean(
        'Close Won on Sale', default=True,
        help='Mark an opportunity Closed Won when one of its quotes is confirmed.')
    modern_crm_activate_on_signature = fields.Boolean(
        'Activate Signed Contracts', default=True,
        help='Activate a contract as soon as every signer has signed it.')
    modern_crm_confirm_on_signature = fields.Boolean(
        'Confirm Quote on Signature', default=True,
        help="Turn a contract's quote into a sales order as soon as every signer has signed it.")
    modern_crm_invoice_on_signature = fields.Boolean(
        'Invoice on Signature',
        help='After confirming the quote of a signed contract, draft its invoice.')
    modern_crm_web_to_lead = fields.Boolean(
        'Web-to-Lead Form',
        help='Publish a form at /crm/web-to-lead that creates a lead for each submission.')
    modern_crm_web_lead_user_id = fields.Many2one(
        'res.users', string='Web Lead Owner', domain="[('share', '=', False)]",
        help='Who gets the leads from the Web-to-Lead form. Leave empty to leave them unassigned.')
    modern_crm_web_lead_team_id = fields.Many2one('crm.team', string='Web Lead Sales Team')

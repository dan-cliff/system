from odoo import fields, models


class ModernCrmContractTemplate(models.Model):
    _name = 'modern.crm.contract.template'
    _description = 'CRM Contract Template'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', index=True,
        help='Leave empty to use the template in every company.')
    term_months = fields.Integer('Contract Term (months)', default=12)
    body = fields.Html(
        'Contract Text', translate=True, sanitize='email_outgoing',
        help='The contract text. Use placeholders such as <t t-out="object.partner_id.name"/> '
             '(object is the contract) to fill in the account, opportunity, quote and dates.')
    countersigner_id = fields.Many2one(
        'res.users', string='Countersigned By',
        domain="[('share', '=', False)]",
        help='Someone from your company who signs after the customer. Leave empty when only the '
             'customer signs.')
    # what the editor's Dynamic Placeholder picker offers fields from
    render_model = fields.Char(compute='_compute_render_model')

    def _compute_render_model(self):
        self.render_model = 'modern.crm.contract'

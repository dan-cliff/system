from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    purchase_account_type_ids = fields.Many2many(
        'advanced.account.type', 'res_company_purchase_account_type_rel', 'company_id', 'type_id',
        string='Account Types to Purchase From',
        help='Which Account Types are considered Suppliers and can be selected in the Suppliers field? '
             'Leave empty to allow every Account.')

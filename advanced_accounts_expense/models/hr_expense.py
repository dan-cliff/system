from odoo import fields, models


class HrExpense(models.Model):
    _name = 'hr.expense'
    _inherit = ['hr.expense', 'advanced.accounts.mixin']
    _adv_partner_field = 'vendor_id'

    adv_account_id = fields.Many2one(string='Vendor Account')
    adv_contact_id = fields.Many2one(string='Vendor Contact')

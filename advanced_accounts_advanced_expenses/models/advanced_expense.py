from odoo import fields, models


class AdvancedExpense(models.Model):
    _name = 'advanced.expense'
    _inherit = ['advanced.expense', 'advanced.accounts.mixin']
    _adv_partner_field = 'vendor_id'

    adv_account_id = fields.Many2one(string='Vendor Account')
    adv_contact_id = fields.Many2one(string='Vendor Contact')

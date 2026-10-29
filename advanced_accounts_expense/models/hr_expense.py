from odoo import models


class HrExpense(models.Model):
    _name = 'hr.expense'
    _inherit = ['hr.expense', 'advanced.accounts.mixin']
    _adv_partner_field = 'vendor_id'

from odoo import models


class RecurringPayment(models.Model):
    _name = 'recurring.payment'
    _inherit = ['recurring.payment', 'advanced.accounts.mixin']

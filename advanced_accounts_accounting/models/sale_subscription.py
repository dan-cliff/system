from odoo import models


class SaleSubscription(models.Model):
    _name = 'sale.subscription'
    _inherit = ['sale.subscription', 'advanced.accounts.mixin']

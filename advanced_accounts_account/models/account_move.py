from odoo import models


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'advanced.accounts.mixin']

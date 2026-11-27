from odoo import models


class PosOrder(models.Model):
    _name = 'pos.order'
    _inherit = ['pos.order', 'advanced.accounts.mixin']

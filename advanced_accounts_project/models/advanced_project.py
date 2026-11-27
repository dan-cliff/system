from odoo import models


class AdvancedProject(models.Model):
    _name = 'advanced.project'
    _inherit = ['advanced.project', 'advanced.accounts.mixin']

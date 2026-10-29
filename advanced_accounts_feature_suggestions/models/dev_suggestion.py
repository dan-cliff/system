from odoo import models


class DevSuggestion(models.Model):
    _name = 'dev.suggestion'
    _inherit = ['dev.suggestion', 'advanced.accounts.mixin']

from odoo import models


class Checklist(models.Model):
    _name = 'checklist.checklist'
    _inherit = ['checklist.checklist', 'advanced.accounts.mixin']
    # Checklists had no customer field: the Account and Contact are their own.
    # (Completed By (Contact) is the person who filled in a public link.)
    _adv_partner_field = False

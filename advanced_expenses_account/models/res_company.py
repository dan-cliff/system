from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    expense_journal_id = fields.Many2one(
        'account.journal', string='Expense Journal', check_company=True,
        domain="[('type', '=', 'purchase'), ('company_id', '=', id)]",
        help='Journal of the bills created for expenses. Empty: the first purchase journal.')

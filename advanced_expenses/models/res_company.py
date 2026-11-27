from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    expense_manager_approval = fields.Boolean(
        string='Manager Approval', default=True,
        help='Submitted expenses wait for approval by the employee\'s Expense Approver (or manager). '
             'Off: submitting an expense approves it straight away.')
    expense_duplicate_warning = fields.Boolean(
        string='Warn About Duplicates', default=True,
        help='Flag expenses of the same employee with the same date and total.')

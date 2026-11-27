"""Link the copied expenses to the journal entries of Odoo's Expenses.

Runs when Expenses installs this module while taking over from hr_expense
(hr_expense's tables are still there, it is uninstalled at the end of the same
install): expenses get their journal entry and account, and categories the
expense account of the product they were copied from.
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    env = env(context=dict(env.context, tracking_disable=True, mail_notrack=True))
    cr = env.cr
    cr.execute("SELECT to_regclass('hr_expense') IS NOT NULL")
    if not cr.fetchone()[0]:
        return
    Expense = env['advanced.expense'].sudo().with_context(active_test=False)
    cr.execute("SELECT id, account_move_id, account_id FROM hr_expense")
    legacy = {row[0]: row[1:] for row in cr.fetchall()}
    expenses = Expense.search([('legacy_hr_expense_id', 'in', list(legacy))])
    Move = env['account.move'].sudo()
    linked = 0
    for expense in expenses:
        move_id, account_id = legacy[expense.legacy_hr_expense_id]
        vals = {}
        if account_id:
            vals['account_id'] = account_id
        if move_id and Move.browse(move_id).exists():
            vals['account_move_id'] = move_id
            linked += 1
        if vals:
            expense.write(vals)
    Category = env['advanced.expense.category'].sudo().with_context(active_test=False)
    for category in Category.search([('legacy_product_id', '!=', False)]):
        product = env['product.product'].sudo().browse(category.legacy_product_id).exists()
        if not product:
            continue
        for company in env['res.company'].sudo().search([]):
            product_c = product.with_company(company)
            account = product_c.property_account_expense_id or product_c.categ_id.property_account_expense_categ_id
            if account:
                category.with_company(company).account_id = account
    _logger.info('Expenses: linked %s expenses to their Odoo Expenses journal entries', linked)

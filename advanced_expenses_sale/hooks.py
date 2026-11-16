"""Keep the sales orders of Odoo's Expenses (sale_expense) on the copied expenses.

Runs when Expenses installs this module while taking over from hr_expense
(its tables are still there until the end of the same install).
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    env = env(context=dict(env.context, tracking_disable=True, mail_notrack=True))
    cr = env.cr
    cr.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'hr_expense' AND column_name = 'sale_order_id'""")
    if not cr.fetchone():
        return
    cr.execute("SELECT id, sale_order_id, sale_order_line_id FROM hr_expense WHERE sale_order_id IS NOT NULL")
    legacy = {row[0]: row[1:] for row in cr.fetchall()}
    expenses = env['advanced.expense'].sudo().search([('legacy_hr_expense_id', 'in', list(legacy))])
    Order, Line = env['sale.order'].sudo(), env['sale.order.line'].sudo()
    for expense in expenses:
        order_id, line_id = legacy[expense.legacy_hr_expense_id]
        vals = {'sale_order_id': order_id if Order.browse(order_id).exists() else False}
        if line_id and Line.browse(line_id).exists():
            vals['sale_order_line_id'] = line_id
        expense.write(vals)
    _logger.info('Expenses: kept the sales order of %s expenses', len(expenses))

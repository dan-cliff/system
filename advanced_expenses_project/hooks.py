"""Keep the projects of the expenses of Odoo's Expenses (project_hr_expense).

Odoo books an expense to a project through the project's analytic account;
copied expenses whose analytic distribution names a project's account get that
project. Runs while hr_expense's tables are still there (it is uninstalled at
the end of the same install).
"""
import json
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    env = env(context=dict(env.context, tracking_disable=True, mail_notrack=True))
    cr = env.cr
    cr.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'hr_expense' AND column_name = 'analytic_distribution'""")
    if not cr.fetchone() or 'account_id' not in env['project.project']._fields:
        return
    cr.execute("SELECT id, analytic_distribution FROM hr_expense WHERE analytic_distribution IS NOT NULL")
    rows = cr.fetchall()
    projects = env['project.project'].sudo().with_context(active_test=False).search([('account_id', '!=', False)])
    by_account = {project.account_id.id: project for project in projects}
    Expense = env['advanced.expense'].sudo()
    count = 0
    for old_id, distribution in rows:
        if isinstance(distribution, str):
            distribution = json.loads(distribution)
        account_ids = [int(a) for key in (distribution or {}) for a in str(key).split(',') if a.isdigit()]
        project = next((by_account[a] for a in account_ids if a in by_account), None)
        if not project:
            continue
        expense = Expense.search([('legacy_hr_expense_id', '=', old_id)], limit=1)
        if expense:
            expense.project_id = project
            count += 1
    _logger.info('Expenses: kept the project of %s expenses', count)

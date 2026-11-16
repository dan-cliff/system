"""Take over from Odoo's Expenses app (hr_expense) when Expenses is installed.

When hr_expense is installed, its data is brought across so it can be
uninstalled straight away:

* the products used for expenses become Expense Categories (a product with a
  cost becomes a category with that Unit Cost);
* expenses, keeping who created them and when, their state, amounts, vendor,
  approval and the Organisation units;
* their receipts (attachments), messages and followers move to the new
  expenses; submitted expenses get a new approval activity;
* the Expense approver of each employee;
* access: Expenses Administrators stay administrators, All Approvers can
  create, edit and approve every expense, Team Approvers their team's, every
  other employee user their own; billing users of Accounting can pay.

The integrations matching what was installed are installed with it
(Accounting always, as Odoo's Expenses needs it; Sales re-invoicing with
sale_expense; Projects with project_hr_expense; vendor Accounts and Contacts
with advanced_accounts_expense). Their own install hooks copy the journal
entries, sales orders and projects of the expenses while hr_expense is still
loaded. hr_expense, and every module that needs it, is then uninstalled at
the end of the same install.
"""
import logging

from odoo import Command

_logger = logging.getLogger(__name__)

BATCH = 500
STATE_MAP = {
    'draft': 'draft',
    'submitted': 'submitted',
    'approved': 'approved',
    # Accounting's bridge turns these into Posted from their journal entry.
    'posted': 'approved',
    'in_payment': 'paid',
    'paid': 'paid',
    'refused': 'refused',
}
ORG_FIELDS = ('org_division_id', 'org_business_unit_id', 'org_location_id', 'org_department_id')
# Installed module -> integration installed with Expenses.
INTEGRATIONS = {
    'hr_expense': 'advanced_expenses_account',
    'sale_expense': 'advanced_expenses_sale',
    'project_hr_expense': 'advanced_expenses_project',
    'advanced_accounts_expense': 'advanced_accounts_advanced_expenses',
}


def post_init_hook(env):
    env = env(context=dict(
        env.context, active_test=False, tracking_disable=True, mail_create_nolog=True,
        mail_create_nosubscribe=True, mail_notrack=True,
    ))
    if 'hr.expense' not in env:
        return
    importer = _Importer(env)
    importer.import_categories()
    importer.import_expenses()
    importer.import_employee_approvers()
    importer.import_access()
    _install_integrations(env)
    _uninstall_hr_expense(env)


def _installed(env, names):
    return env['ir.module.module'].sudo().search([
        ('name', 'in', list(names)), ('state', 'in', ('installed', 'to upgrade', 'to install')),
    ])


def _install_integrations(env):
    installed = set(_installed(env, INTEGRATIONS).mapped('name'))
    wanted = [INTEGRATIONS[name] for name in INTEGRATIONS if name in installed]
    modules = env['ir.module.module'].sudo().search([('name', 'in', wanted), ('state', '=', 'uninstalled')])
    for module in modules:
        try:
            module.button_install()
        except Exception as error:  # noqa: BLE001 - the integration can still be switched on in Settings
            _logger.warning('Expenses: could not install %s: %s', module.name, error)


def _uninstall_hr_expense(env):
    """Uninstall Odoo's Expenses (and what depends on it) at the end of this install."""
    module = env['ir.module.module'].sudo().search([('name', '=', 'hr_expense'),
                                                    ('state', 'in', ('installed', 'to upgrade'))])
    if module:
        _logger.info('Expenses: uninstalling Odoo Expenses (hr_expense) and %s',
                     ', '.join(module.downstream_dependencies().mapped('name')) or 'no other module')
        module.button_uninstall()


class _Importer:

    def __init__(self, env):
        self.env = env
        self.category_map = {}   # product.product id -> category id
        self.expense_map = {}    # hr.expense id -> advanced.expense id

    # ── Categories ────────────────────────────────────────────────────────
    def import_categories(self):
        env = self.env
        Category = env['advanced.expense.category'].sudo()
        Product = env['product.product'].sudo()
        products = env['hr.expense'].sudo().search([]).product_id
        if 'can_be_expensed' in Product._fields:
            products |= Product.search([('can_be_expensed', '=', True)])
        existing = {c.name.strip().lower(): c for c in Category.search([])}
        for product in products:
            name = product.name or product.display_name
            category = existing.get((name or '').strip().lower())
            cost = product.standard_price or 0.0
            if not category:
                category = Category.create({
                    'name': name,
                    'active': product.active,
                    'company_id': product.company_id.id,
                    'cost': cost,
                    'unit_name': product.uom_id.name if cost else False,
                    'receipt_required': not cost,
                })
                existing[name.strip().lower()] = category
            category.legacy_product_id = product.id
            self.category_map[product.id] = category.id
        _logger.info('Expenses: %s expense products mapped to categories', len(self.category_map))

    # ── Expenses ──────────────────────────────────────────────────────────
    def import_expenses(self):
        env = self.env
        Old = env['hr.expense'].sudo()
        New = env['advanced.expense'].sudo()
        olds = Old.search([], order='id')
        other = env.ref('advanced_expenses.expense_category_other')
        org_fields = [f for f in ORG_FIELDS if f in Old._fields and f in New._fields]

        def values(old):
            has_cost = bool(old.product_id and old.product_id.standard_price)
            vals = {
                'name': old.name or old.product_id.name or 'Expense',
                'employee_id': old.employee_id.id,
                'date': old.date or old.create_date.date(),
                'category_id': self.category_map.get(old.product_id.id, other.id),
                'quantity': old.quantity if has_cost else 1.0,
                'unit_cost': old.price_unit if has_cost else 0.0,
                'currency_id': old.currency_id.id or old.company_id.currency_id.id,
                'total_amount': old.total_amount_currency,
                'tax_amount': old.tax_amount_currency,
                'paid_by': 'company' if old.payment_mode == 'company_account' else 'employee',
                'vendor_id': old.vendor_id.id,
                'note': old.description,
                'company_id': old.company_id.id,
                'state': STATE_MAP.get(old.state, 'draft'),
                'approved_date': old.approval_date,
                'approved_by_id': old.manager_id.id if old.approval_state == 'approve' else False,
                'legacy_hr_expense_id': old.id,
            }
            if old.state in ('submitted', 'approved', 'posted', 'in_payment', 'paid'):
                vals['submitted_date'] = old.approval_date or old.write_date
            if vals['state'] == 'paid':
                vals['paid_date'] = (old.account_move_id.invoice_date or old.write_date.date()) \
                    if 'account_move_id' in old._fields and old.account_move_id else old.write_date.date()
            for name in org_fields:
                vals[name] = old[name].id
            return vals

        pairs, skipped = [], 0
        for start in range(0, len(olds), BATCH):
            chunk = olds[start:start + BATCH]
            try:
                with env.cr.savepoint():
                    news = New.create([values(old) for old in chunk])
                    news.flush_recordset()
                done = list(zip(chunk, news))
            except Exception:  # noqa: BLE001 - copy the rest one by one, report the ones that fail
                done = []
                for old in chunk:
                    try:
                        with env.cr.savepoint():
                            new = New.create(values(old))
                            new.flush_recordset()
                        done.append((old, new))
                    except Exception as error:  # noqa: BLE001
                        skipped += 1
                        _logger.warning('Expenses: could not copy hr.expense %s: %s', old.id, error)
            for old, new in done:
                self.expense_map[old.id] = new.id
                pairs.append((new.id, old.id))
        self._copy_audit(pairs)
        self._move_mail(pairs)
        for old, new in ((Old.browse(o), New.browse(n)) for n, o in pairs):
            if old.message_main_attachment_id:
                new.message_main_attachment_id = old.message_main_attachment_id.id
        New.browse([n for n, _o in pairs]).filtered(lambda e: e.state == 'submitted')._schedule_approval_activity()
        _logger.info('Expenses: copied %s Odoo expenses (%s skipped)', len(pairs), skipped)

    def _pairs_sql(self, pairs):
        return [n for n, _o in pairs], [o for _n, o in pairs]

    def _copy_audit(self, pairs):
        """Keep create_uid / create_date (record rules use create_uid)."""
        cr = self.env.cr
        for start in range(0, len(pairs), BATCH):
            new_ids, old_ids = self._pairs_sql(pairs[start:start + BATCH])
            cr.execute("""
                UPDATE advanced_expense AS n
                   SET create_uid = o.create_uid, create_date = o.create_date
                  FROM hr_expense AS o, (SELECT unnest(%s::int[]) AS new_id, unnest(%s::int[]) AS old_id) AS m
                 WHERE n.id = m.new_id AND o.id = m.old_id
            """, (new_ids, old_ids))

    def _move_mail(self, pairs):
        """Move the receipts, messages and followers of the Odoo expenses to the new ones."""
        cr = self.env.cr
        self.env.flush_all()
        for start in range(0, len(pairs), BATCH):
            new_ids, old_ids = self._pairs_sql(pairs[start:start + BATCH])
            mapping = "(SELECT unnest(%s::int[]) AS new_id, unnest(%s::int[]) AS old_id)"
            cr.execute(f"""
                UPDATE ir_attachment AS a SET res_model = 'advanced.expense', res_id = m.new_id
                  FROM {mapping} AS m
                 WHERE a.res_model = 'hr.expense' AND a.res_id = m.old_id
            """, (new_ids, old_ids))
            # Messages with something to read (tracking-only messages lose their values
            # when hr_expense's fields are removed).
            cr.execute(f"""
                UPDATE mail_message AS msg SET model = 'advanced.expense', res_id = m.new_id
                  FROM {mapping} AS m
                 WHERE msg.model = 'hr.expense' AND msg.res_id = m.old_id
                   AND (msg.message_type IN ('comment', 'email', 'email_outgoing')
                        OR COALESCE(msg.body::text, '') NOT IN ('', '<p></p>'))
            """, (new_ids, old_ids))
            cr.execute(f"""
                UPDATE mail_followers AS f SET res_model = 'advanced.expense', res_id = m.new_id
                  FROM {mapping} AS m
                 WHERE f.res_model = 'hr.expense' AND f.res_id = m.old_id
                   AND NOT EXISTS (SELECT 1 FROM mail_followers g
                                    WHERE g.res_model = 'advanced.expense' AND g.res_id = m.new_id
                                      AND g.partner_id = f.partner_id)
            """, (new_ids, old_ids))
        self.env.invalidate_all()

    # ── Employees ─────────────────────────────────────────────────────────
    def import_employee_approvers(self):
        Employee = self.env['hr.employee'].sudo()
        if 'expense_manager_id' not in Employee._fields:
            return
        employees = Employee.search([('expense_manager_id', '!=', False)])
        for manager, group in employees.grouped('expense_manager_id').items():
            group.write({'expense_approver_id': manager.id})
        _logger.info('Expenses: copied the Expense approver of %s employees', len(employees))

    # ── Access ────────────────────────────────────────────────────────────
    def _users(self, xmlid):
        group = self.env.ref(xmlid, raise_if_not_found=False)
        if not group:
            return self.env['res.users']
        users = group.all_user_ids if 'all_user_ids' in group._fields else group.user_ids
        return users.filtered(lambda u: not u.share)

    def _grant(self, users, *keys):
        for key in keys:
            group = self.env.ref(f'advanced_expenses.group_{key}')
            group.sudo().write({'user_ids': [Command.link(user.id) for user in users]})

    def import_access(self):
        env = self.env
        admins = self._users('hr_expense.group_hr_expense_manager')
        all_approvers = self._users('hr_expense.group_hr_expense_user') - admins
        team_approvers = self._users('hr_expense.group_hr_expense_team_approver') - admins - all_approvers
        employees = env['hr.employee'].sudo().search([('user_id', '!=', False)]).user_id.filtered(
            lambda u: not u.share and u.active)
        self._grant(admins, 'expenses_admin')
        self._grant(all_approvers, 'expense_edit_all', 'expense_approve_any', 'expense_delete_own')
        self._grant(team_approvers, 'expense_edit_team', 'expense_approve', 'expense_delete_own')
        self._grant(employees - admins - all_approvers - team_approvers, 'expense_edit_own', 'expense_delete_own')
        payers = self._users('account.group_account_invoice') - admins
        self._grant(payers, 'expense_view_all', 'expense_pay')

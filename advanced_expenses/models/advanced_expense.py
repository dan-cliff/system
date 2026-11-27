# -*- coding: utf-8 -*-
import json
import logging
from datetime import date as dt_date

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import expense_ai

_logger = logging.getLogger(__name__)

# The expense workflow. Code depends on these, so they stay a fixed selection
# (CLAUDE.md > Choice fields); integrations add theirs with selection_add
# (e.g. Accounting's "Posted").
EXPENSE_STATES = [
    ('draft', 'Draft'),
    ('submitted', 'Submitted'),
    ('approved', 'Approved'),
    ('paid', 'Paid'),
    ('refused', 'Refused'),
]
# Who paid: the employee is reimbursed, a company card needs no reimbursement.
# Code depends on it (reimbursement, bills), so it stays a fixed selection.
PAID_BY = [
    ('employee', 'Employee (to reimburse)'),
    ('company', 'Company'),
]
# What can't change once an expense has been submitted.
LOCKED_FIELDS = {
    'name', 'employee_id', 'date', 'category_id', 'quantity', 'unit_cost', 'total_amount', 'tax_amount',
    'currency_id', 'paid_by', 'company_id',
}


class AdvancedExpense(models.Model):
    _name = 'advanced.expense'
    _description = 'Expense'
    _inherit = ['mail.thread.main.attachment', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _check_company_auto = True
    _mail_post_access = 'read'
    _rec_names_search = ['name', 'reference']
    # Expenses take their Organisation units from the employee.
    _org_parent_field = 'employee_id'

    reference = fields.Char(string='Reference', readonly=True, copy=False, index='trigram',
                            default=lambda self: _('New'))
    name = fields.Char(string='Description', required=True, tracking=True, index='trigram')
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True, tracking=True, check_company=True,
        default=lambda self: self._default_employee_id(),
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    user_id = fields.Many2one(related='employee_id.user_id', string='User', store=True, index=True)
    department_id = fields.Many2one(related='employee_id.department_id', string='Department', store=True)
    approver_user_id = fields.Many2one(
        'res.users', string='Approver', compute='_compute_approver_user_id', store=True, index=True,
        help="The employee's Expense Approver (Personnel employee form), or else their manager.")
    date = fields.Date(string='Expense Date', required=True, tracking=True, default=fields.Date.context_today)
    category_id = fields.Many2one(
        'advanced.expense.category', string='Category', required=True, tracking=True, index=True,
        check_company=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    category_description = fields.Text(related='category_id.description')
    has_fixed_cost = fields.Boolean(compute='_compute_has_fixed_cost')
    unit_name = fields.Char(related='category_id.unit_name')
    quantity = fields.Float(string='Quantity', default=1.0, digits='Product Unit')
    unit_cost = fields.Float(string='Unit Cost', digits='Product Price', compute='_compute_unit_cost',
                             store=True, readonly=False, precompute=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.company.currency_id)
    company_currency_id = fields.Many2one(related='company_id.currency_id', string='Company Currency')
    total_amount = fields.Monetary(string='Total', currency_field='currency_id', tracking=True,
                                   compute='_compute_total_amount', store=True, readonly=False, precompute=True)
    tax_amount = fields.Monetary(string='Tax Included', currency_field='currency_id',
                                 help='The tax (e.g. GST or VAT) included in the total, from the receipt.')
    total_amount_company = fields.Monetary(
        string='Total in Company Currency', currency_field='company_currency_id',
        compute='_compute_total_amount_company', store=True)
    is_multiple_currency = fields.Boolean(compute='_compute_is_multiple_currency')
    paid_by = fields.Selection(PAID_BY, string='Paid By', required=True, default='employee', tracking=True)
    vendor_id = fields.Many2one('res.partner', string='Vendor', tracking=True, check_company=True)
    note = fields.Text(string='Notes')
    state = fields.Selection(EXPENSE_STATES, string='Status', default='draft', required=True, readonly=True,
                             copy=False, tracking=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True, tracking=True,
                                 default=lambda self: self.env.company)
    submitted_date = fields.Datetime(string='Submitted On', readonly=True, copy=False)
    approved_date = fields.Datetime(string='Approved On', readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)
    paid_date = fields.Date(string='Paid On', readonly=True, copy=False)
    refused_reason = fields.Text(string='Refusal Reason', readonly=True, copy=False)
    receipt_count = fields.Integer(string='Receipts', compute='_compute_receipt_count')
    duplicate_expense_ids = fields.Many2many('advanced.expense', compute='_compute_duplicate_expense_ids',
                                             string='Possible Duplicates')
    can_approve = fields.Boolean(compute='_compute_permissions')
    can_pay = fields.Boolean(compute='_compute_permissions')
    is_mine = fields.Boolean(compute='_compute_permissions')
    ai_available = fields.Boolean(compute='_compute_ai_available')
    # Odoo Expenses record this expense was copied from (see hooks.py).
    legacy_hr_expense_id = fields.Integer(readonly=True, copy=False, index='btree_not_null')

    _positive_quantity = models.Constraint('CHECK(quantity >= 0)', 'The quantity cannot be negative.')

    # ------------------------------------------------------------------
    # Defaults and computes
    # ------------------------------------------------------------------
    @api.model
    def _default_employee_id(self):
        return self.env.user.with_company(self.env.company).employee_id

    @api.depends('employee_id.expense_approver_id', 'employee_id.parent_id.user_id')
    def _compute_approver_user_id(self):
        for expense in self:
            employee = expense.employee_id.sudo()
            expense.approver_user_id = employee.expense_approver_id or employee.parent_id.user_id

    @api.depends('category_id.cost')
    def _compute_has_fixed_cost(self):
        for expense in self:
            expense.has_fixed_cost = bool(expense.category_id.cost)

    @api.depends('category_id')
    def _compute_unit_cost(self):
        for expense in self:
            if expense.category_id.cost:
                expense.unit_cost = expense.category_id.cost
            elif not expense.unit_cost:
                expense.unit_cost = 0.0

    @api.depends('quantity', 'unit_cost', 'category_id', 'currency_id')
    def _compute_total_amount(self):
        for expense in self:
            if expense.category_id.cost:
                amount = expense.quantity * expense.unit_cost
                expense.total_amount = expense.currency_id.round(amount) if expense.currency_id else amount
            elif not expense.total_amount:
                expense.total_amount = 0.0

    @api.depends('total_amount', 'currency_id', 'company_id', 'date')
    def _compute_total_amount_company(self):
        for expense in self:
            company_currency = expense.company_id.currency_id
            if not expense.currency_id or not company_currency or expense.currency_id == company_currency:
                expense.total_amount_company = expense.total_amount
            else:
                expense.total_amount_company = expense.currency_id._convert(
                    expense.total_amount, company_currency, expense.company_id,
                    expense.date or fields.Date.context_today(expense))

    @api.depends('currency_id', 'company_id')
    def _compute_is_multiple_currency(self):
        for expense in self:
            expense.is_multiple_currency = expense.currency_id != expense.company_id.currency_id

    def _compute_receipt_count(self):
        counts = dict(self.env['ir.attachment'].sudo()._read_group(
            [('res_model', '=', self._name), ('res_id', 'in', self.ids)], ['res_id'], ['__count']))
        for expense in self:
            expense.receipt_count = counts.get(expense.id, 0)

    @api.depends('employee_id', 'date', 'total_amount', 'currency_id', 'state')
    def _compute_duplicate_expense_ids(self):
        self.duplicate_expense_ids = False
        candidates = self.filtered(lambda e: e.employee_id and e.date and e.total_amount
                                   and e.state != 'refused' and e.company_id.expense_duplicate_warning)
        if not candidates:
            return
        others = self.sudo().search([
            ('employee_id', 'in', candidates.employee_id.ids),
            ('date', 'in', list(set(candidates.mapped('date')))),
            ('state', '!=', 'refused'),
        ])
        for expense in candidates:
            expense.duplicate_expense_ids = others.filtered(
                lambda o: o.id != expense._origin.id and o.employee_id == expense.employee_id
                and o.date == expense.date and o.currency_id == expense.currency_id
                and o.currency_id.compare_amounts(o.total_amount, expense.total_amount) == 0)

    @api.depends_context('uid')
    @api.depends('state', 'employee_id', 'approver_user_id')
    def _compute_permissions(self):
        user = self.env.user
        can_pay = user.has_group('advanced_expenses.group_expense_pay')
        for expense in self:
            expense.is_mine = expense._is_mine()
            expense.can_approve = expense.state == 'submitted' and expense._user_can_approve()
            expense.can_pay = can_pay and expense.state == 'approved'

    def _compute_ai_available(self):
        available = expense_ai.ai_available(self.env)
        for expense in self:
            expense.ai_available = available

    # ------------------------------------------------------------------
    # Access helpers
    # ------------------------------------------------------------------
    def _is_mine(self):
        self.ensure_one()
        user = self.env.user
        return self.employee_id.user_id == user or (self.create_uid == user if self.id else True)

    def _team_employees(self, user=None):
        """The user's employees and everyone under them in the org chart."""
        user = user or self.env.user
        if not user.employee_ids:
            return self.env['hr.employee']
        return self.env['hr.employee'].sudo().search([('id', 'child_of', user.employee_ids.ids)])

    def _user_can_approve(self, user=None):
        """Whether ``user`` may approve or refuse this expense. No one approves their own expenses
        except the Expenses Administrator."""
        self.ensure_one()
        user = user or self.env.user
        if user.has_group('advanced_expenses.group_expenses_admin'):
            return True
        if self.employee_id.user_id == user:
            return False
        if user.has_group('advanced_expenses.group_expense_approve_any'):
            return True
        if user.has_group('advanced_expenses.group_expense_approve'):
            return self.approver_user_id == user or self.employee_id in self._team_employees(user)
        return False

    def _check_can_submit(self):
        for expense in self:
            if expense._is_mine():
                continue
            # Someone else's expense: only those who may edit it can submit it.
            expense.check_access('write')

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('reference') or vals['reference'] == _('New'):
                vals['reference'] = self.env['ir.sequence'].sudo().next_by_code('advanced.expense') or _('New')
        expenses = super().create(vals_list)
        expenses._subscribe_employee()
        return expenses

    def write(self, vals):
        if LOCKED_FIELDS & set(vals) and not self.env.su \
                and not self.env.user.has_group('advanced_expenses.group_expenses_admin'):
            locked = self.filtered(lambda e: e.state not in ('draft', 'refused'))
            if locked:
                raise UserError(_('%s has been submitted and can no longer be changed. Reset it to draft first.',
                                  ', '.join(locked.mapped('display_name'))))
        result = super().write(vals)
        if 'employee_id' in vals:
            self._subscribe_employee()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if self.env.user.has_group('advanced_expenses.group_expenses_admin'):
            return
        if any(expense.state not in ('draft', 'refused') for expense in self):
            raise UserError(_('Only draft or refused expenses can be deleted.'))

    @api.depends('reference', 'name')
    def _compute_display_name(self):
        for expense in self:
            if expense.reference and expense.reference != _('New'):
                expense.display_name = '%s %s' % (expense.reference, expense.name or '')
            else:
                expense.display_name = expense.name or _('New Expense')

    def _subscribe_employee(self):
        for expense in self:
            partner = expense.employee_id.user_id.partner_id
            if partner:
                expense.sudo().message_subscribe(partner_ids=partner.ids)

    @api.constrains('total_amount', 'tax_amount')
    def _check_amounts(self):
        for expense in self:
            # Totals can be negative (a refund), the tax included can't be more than the total.
            if expense.currency_id.compare_amounts(abs(expense.tax_amount), abs(expense.total_amount)) > 0:
                raise ValidationError(_('The tax included cannot be more than the total.'))

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _check_ready_to_submit(self):
        for expense in self:
            if expense.state not in ('draft', 'refused'):
                raise UserError(_('%s has already been submitted.', expense.display_name))
            if expense.currency_id.is_zero(expense.total_amount):
                raise UserError(_('Enter the total of %s before submitting it.', expense.display_name))
            if expense.category_id.receipt_required and not expense.receipt_count:
                raise UserError(_('%(category)s expenses need a receipt: attach it to %(expense)s before '
                                  'submitting.', category=expense.category_id.name, expense=expense.display_name))

    def action_submit(self):
        self._check_can_submit()
        self._check_ready_to_submit()
        now = fields.Datetime.now()
        for expense in self.sudo():
            expense.write({'state': 'submitted', 'submitted_date': now, 'refused_reason': False})
            if not expense.company_id.expense_manager_approval:
                expense._do_approve(note=_('Approved automatically (Manager Approval is off).'))
            else:
                expense._schedule_approval_activity()
        return True

    def _schedule_approval_activity(self):
        activity_type = self.env.ref('advanced_expenses.mail_activity_expense_approval', raise_if_not_found=False)
        if not activity_type:
            return
        for expense in self.sudo():
            approver = expense.approver_user_id
            if approver and approver != expense.employee_id.user_id:
                expense.activity_schedule(
                    activity_type_id=activity_type.id, user_id=approver.id,
                    summary=_('Approve the expense of %s', expense.employee_id.name))

    def _close_approval_activities(self, feedback=None):
        activity_type = self.env.ref('advanced_expenses.mail_activity_expense_approval', raise_if_not_found=False)
        if not activity_type:
            return
        activities = self.sudo().activity_ids.filtered(lambda a: a.activity_type_id == activity_type)
        if feedback:
            activities.action_feedback(feedback=feedback)
        else:
            activities.unlink()

    def _check_can_approve(self):
        for expense in self:
            if expense.state != 'submitted':
                raise UserError(_('%s is not waiting for approval.', expense.display_name))
            if not expense._user_can_approve():
                raise UserError(_('You cannot approve or refuse %s.', expense.display_name))

    def action_approve(self):
        self._check_can_approve()
        self.sudo()._do_approve()
        return True

    def _do_approve(self, note=None):
        now = fields.Datetime.now()
        for expense in self:
            expense.write({'state': 'approved', 'approved_date': now, 'approved_by_id': self.env.uid})
            expense._close_approval_activities(feedback=_('Approved'))
            expense._notify_employee(note or _('Your expense was approved by %s.', self.env.user.name))
        self._on_approved()

    def _on_approved(self):
        """Hook: integrations act on newly approved expenses (sales order lines, payslips, ...)."""
        return True

    def action_refuse(self):
        self._check_can_approve()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Refuse Expense'),
            'res_model': 'advanced.expense.refuse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_expense_ids': self.ids},
        }

    def _do_refuse(self, reason):
        self._check_can_approve()
        for expense in self.sudo():
            expense.write({'state': 'refused', 'refused_reason': reason})
            expense._close_approval_activities(feedback=_('Refused: %s', reason))
            expense._notify_employee(_('Your expense was refused by %(user)s: %(reason)s',
                                       user=self.env.user.name, reason=reason))
        self.sudo()._on_reset()
        return True

    def action_reset_to_draft(self):
        for expense in self:
            if expense.state in ('submitted', 'refused'):
                if not expense._is_mine() and not expense._user_can_approve():
                    expense.check_access('write')
            elif expense.state == 'approved':
                if not (self.env.user.has_group('advanced_expenses.group_expense_pay')
                        or expense._user_can_approve()):
                    raise UserError(_('Only an approver or someone who pays expenses can reset %s.',
                                      expense.display_name))
            else:
                raise UserError(_('%s cannot be reset to draft.', expense.display_name))
        self.sudo()._on_reset()
        self.sudo().write({'state': 'draft', 'submitted_date': False, 'approved_date': False,
                           'approved_by_id': False})
        self.sudo()._close_approval_activities()
        return True

    def _on_reset(self):
        """Hook: integrations undo what approval did (sales order lines, payslips, ...)."""
        return True

    def _check_can_pay(self):
        if not self.env.user.has_group('advanced_expenses.group_expense_pay'):
            raise UserError(_('You need the "Expenses: Pay" permission to do this.'))

    def action_mark_paid(self):
        self._check_can_pay()
        for expense in self:
            if expense.state != 'approved':
                raise UserError(_('%s is not approved.', expense.display_name))
        self.sudo()._do_mark_paid()
        return True

    def _do_mark_paid(self, paid_date=None):
        for expense in self:
            expense.write({'state': 'paid', 'paid_date': paid_date or fields.Date.context_today(expense)})
            if expense.paid_by == 'employee':
                expense._notify_employee(_('Your expense has been reimbursed.'))

    def _notify_employee(self, message):
        self.ensure_one()
        partner = self.employee_id.user_id.partner_id
        self.sudo().message_post(
            body=escape(message), message_type='notification', subtype_xmlid='mail.mt_note',
            partner_ids=partner.ids if partner and partner != self.env.user.partner_id else [])

    def action_open_duplicates(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Possible Duplicates'),
            'res_model': self._name,
            'view_mode': 'list,form',
            'domain': [('id', 'in', (self.duplicate_expense_ids | self).ids)],
        }

    def action_print(self):
        return self.env.ref('advanced_expenses.action_report_expense').report_action(self)

    # ------------------------------------------------------------------
    # AI receipt reading
    # ------------------------------------------------------------------
    def _ai_receipt(self):
        """The receipt the AI reads: the main attachment, else the newest readable one."""
        self.ensure_one()
        readable = expense_ai.IMAGE_TYPES + (expense_ai.PDF_TYPE,)
        main = self.message_main_attachment_id
        if main and main.mimetype in readable:
            return main.sudo()
        return self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name), ('res_id', '=', self.id), ('mimetype', 'in', list(readable)),
        ], order='id desc', limit=1)

    def get_ai_receipt_description(self):
        """What the overlay tells the user the AI is doing."""
        self.ensure_one()
        self.check_access('read')
        if not expense_ai.ai_available(self.env):
            raise UserError(expense_ai.no_ai_message(self.env))
        receipt = self._ai_receipt()
        if not receipt:
            raise UserError(_('Attach the receipt (a photo or a PDF) to the expense first, then read it with AI.'))
        return {
            'provider': expense_ai.provider_label(self.env),
            'receipt': receipt.name or '',
            'fields': [_('Description'), _('Date'), _('Total'), _('Tax Included'), _('Currency'),
                       _('Vendor'), _('Category')],
        }

    def action_ai_read_receipt(self):
        """Read the attached receipt with the AI and fill in the expense."""
        self.ensure_one()
        if not expense_ai.ai_available(self.env):
            raise UserError(expense_ai.no_ai_message(self.env))
        if self.state not in ('draft', 'refused'):
            raise UserError(_('Only draft expenses can be filled in from their receipt.'))
        if not self._is_mine():
            self.check_access('write')
        receipt = self._ai_receipt()
        if not receipt:
            raise UserError(_('Attach the receipt (a photo or a PDF) to the expense first, then read it with AI.'))
        categories = self.env['advanced.expense.category'].search(
            ['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)])
        answer = expense_ai.ai_read_file(
            self.env, self._ai_receipt_prompt(categories), receipt.raw, receipt.mimetype,
            system='You read receipts and invoices for an expense claim. Answer only with the JSON asked for.',
            schema=self._ai_receipt_schema(categories))
        values = self._ai_parse_receipt(answer)
        self._ai_apply_receipt(values, categories)
        return True

    def _ai_receipt_schema(self, categories):
        text = {'type': 'string'}
        number = {'type': 'number'}
        return expense_ai.json_object(
            description=text, date=text, total=number, tax=number, currency=text, vendor=text,
            category={'type': 'string', 'enum': categories.mapped('name') + ['']},
        )

    def _ai_receipt_prompt(self, categories):
        return (
            'Read the attached receipt and answer with a JSON object with these keys:\n'
            '- "description": a short description of what was bought (at most 8 words), e.g. "Lunch with client"\n'
            '- "date": the date of the purchase as YYYY-MM-DD, or "" if not shown\n'
            '- "total": the total paid, including tax, as a number\n'
            '- "tax": the tax (GST, VAT, sales tax) included in the total as a number, or 0\n'
            '- "currency": the ISO 4217 code of the currency (e.g. AUD, NZD, USD), or ""\n'
            '- "vendor": the name of the business that issued the receipt, or ""\n'
            '- "category": the best matching category from this list, or "": %s\n'
        ) % json.dumps(categories.mapped('name'))

    def _ai_parse_receipt(self, answer):
        text = (answer or '').strip()
        if text.startswith('```'):
            text = text.strip('`')
            text = text[text.find('{'):]
        start, end = text.find('{'), text.rfind('}')
        try:
            values = json.loads(text[start:end + 1]) if start >= 0 else {}
        except ValueError:
            values = {}
        if not isinstance(values, dict) or not values:
            raise UserError(_('The AI could not read the receipt. Check that it is clear and try again.'))
        return values

    def _ai_apply_receipt(self, values, categories):
        vals, read = {}, []
        description = (values.get('description') or '').strip()
        if description:
            vals['name'] = description[:120]
            read.append(_('Description: %s', description))
        try:
            receipt_date = dt_date.fromisoformat((values.get('date') or '').strip()[:10])
        except ValueError:
            receipt_date = False
        if receipt_date:
            vals['date'] = receipt_date
            read.append(_('Date: %s', receipt_date.strftime('%d/%m/%Y')))
        code = (values.get('currency') or '').strip().upper()
        if code:
            currency = self.env['res.currency'].search([('name', '=', code)], limit=1)
            if currency:
                vals['currency_id'] = currency.id
                read.append(_('Currency: %s', code))
        category = categories.filtered(lambda c: c.name == values.get('category'))[:1]
        if category:
            vals['category_id'] = category.id
            read.append(_('Category: %s', category.name))
        if not (category or self.category_id).cost:
            total = values.get('total')
            if isinstance(total, (int, float)) and total > 0:
                vals['total_amount'] = total
                read.append(_('Total: %s', total))
        tax = values.get('tax')
        if isinstance(tax, (int, float)) and tax >= 0:
            vals['tax_amount'] = tax
            read.append(_('Tax Included: %s', tax))
        vendor_name = (values.get('vendor') or '').strip()
        if vendor_name:
            vendor = self.env['res.partner'].search([('name', '=ilike', vendor_name),
                                                     ('company_id', 'in', [False, self.company_id.id])], limit=1)
            if vendor:
                vals['vendor_id'] = vendor.id
            read.append(_('Vendor: %s', vendor_name) if vendor else
                        _('Vendor: %s (not found in Contacts, so not set)', vendor_name))
        if 'tax_amount' in vals and 'total_amount' not in vals and vals['tax_amount'] > self.total_amount:
            vals.pop('tax_amount')
        if vals:
            self.write(vals)
        body = Markup('<p>%s</p><ul>%s</ul>') % (
            _('Read from the receipt by %s:', expense_ai.provider_label(self.env)),
            Markup('').join(Markup('<li>%s</li>') % line for line in read))
        self.message_post(body=body, message_type='comment', subtype_xmlid='mail.mt_note')

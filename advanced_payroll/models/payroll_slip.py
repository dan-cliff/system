# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .payroll_pay_item import CATEGORIES, DEDUCTED_CATEGORIES, GROSS_CATEGORIES
from .payroll_run import RUN_STATES

# Where a payslip line came from. Lines of every source except "manual" are
# rebuilt each time the payslip is computed; integrations add their own
# sources (e.g. timesheets) with selection_add.
LINE_SOURCES = [
    ('manual', 'Entered'),
    ('salary', 'Salary / Standard Hours'),
    ('rule', 'Payroll Rule'),
]
# Where hourly employees' hours come from (Settings › Payroll › Pay Hours From).
# Integrations add theirs and a matching _payroll_hours_vals_<source> method.
HOURS_SOURCES = [('standard', 'Standard Hours')]


class PayrollSlip(models.Model):
    _name = 'payroll.slip'
    _description = 'Payslip'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, name, id desc'
    # Payslips take their Organisation units from the employee's payroll profile.
    _org_parent_field = 'payroll_employee_id'

    name = fields.Char(string='Payslip', compute='_compute_name', store=True)
    run_id = fields.Many2one('payroll.run', string='Pay Run', required=True, index=True, ondelete='cascade',
                             domain="[('state', '=', 'draft')]")
    payroll_employee_id = fields.Many2one(
        'payroll.employee', string='Payroll Employee', required=True, index=True, tracking=True,
        domain="[('country_id', '=', country_id), ('company_id', '=', company_id)]",
    )
    employee_id = fields.Many2one(related='payroll_employee_id.employee_id', string='Employee', store=True,
                                  index=True)
    user_id = fields.Many2one(related='payroll_employee_id.employee_id.user_id', string='User', store=True,
                              index=True)
    company_id = fields.Many2one(related='run_id.company_id', string='Company', store=True, index=True)
    currency_id = fields.Many2one(related='run_id.currency_id')
    country_id = fields.Many2one(related='run_id.country_id', string='Payroll Country', store=True, index=True)
    country_code = fields.Char(related='country_id.code')
    pay_frequency_id = fields.Many2one(related='run_id.pay_frequency_id', store=True)
    date_start = fields.Date(related='run_id.date_start', string='Period From', store=True, index=True)
    date_end = fields.Date(related='run_id.date_end', string='Period To', store=True)
    payment_date = fields.Date(related='run_id.payment_date', string='Payment Date', store=True)
    state = fields.Selection(RUN_STATES, string='Status', default='draft', required=True, readonly=True,
                             copy=False, tracking=True, index=True)
    line_ids = fields.One2many('payroll.slip.line', 'slip_id', string='Lines', copy=True)
    hours = fields.Float(string='Hours Paid', compute='_compute_totals', store=True)
    gross_amount = fields.Monetary(string='Gross Pay', compute='_compute_totals', store=True)
    taxable_amount = fields.Monetary(string='Taxable Pay', compute='_compute_totals', store=True)
    tax_amount = fields.Monetary(string='Tax', compute='_compute_totals', store=True)
    deduction_amount = fields.Monetary(string='Deductions', compute='_compute_totals', store=True)
    reimbursement_amount = fields.Monetary(string='Reimbursements', compute='_compute_totals', store=True)
    net_amount = fields.Monetary(string='Net Pay', compute='_compute_totals', store=True)
    employer_amount = fields.Monetary(string='Employer Contributions', compute='_compute_totals', store=True)
    cost_amount = fields.Monetary(string='Employer Cost', compute='_compute_totals', store=True,
                                  help='Gross pay, reimbursements and employer contributions.')
    computed_date = fields.Datetime(string='Computed On', readonly=True, copy=False)
    note = fields.Text(string='Note on Payslip', help='Printed on the payslip.')

    _employee_run_unique = models.Constraint(
        'UNIQUE(run_id, payroll_employee_id)', 'An employee can only have one payslip in a pay run.')

    @api.depends('payroll_employee_id.name', 'date_start', 'date_end')
    def _compute_name(self):
        for slip in self:
            dates = ' – '.join(d.strftime('%d/%m/%Y') for d in (slip.date_start, slip.date_end) if d)
            slip.name = ' '.join(part for part in (slip.payroll_employee_id.name, dates) if part) or _('New Payslip')

    @api.depends('line_ids.amount', 'line_ids.category', 'line_ids.quantity', 'line_ids.is_taxable',
                 'line_ids.calculation')
    def _compute_totals(self):
        for slip in self:
            lines = slip.line_ids
            gross = lines.filtered(lambda l: l.category in GROSS_CATEGORIES)
            slip.hours = sum(gross.filtered(lambda l: l.calculation == 'hours').mapped('quantity'))
            slip.gross_amount = sum(gross.mapped('amount'))
            slip.taxable_amount = sum(lines.filtered('is_taxable').mapped('amount'))
            slip.tax_amount = sum(lines.filtered(lambda l: l.category == 'tax').mapped('amount'))
            slip.deduction_amount = sum(lines.filtered(lambda l: l.category == 'deduction').mapped('amount'))
            slip.reimbursement_amount = sum(lines.filtered(lambda l: l.category == 'reimbursement').mapped('amount'))
            slip.employer_amount = sum(lines.filtered(lambda l: l.category == 'employer').mapped('amount'))
            slip.net_amount = (slip.gross_amount + slip.reimbursement_amount
                               - slip.tax_amount - slip.deduction_amount)
            slip.cost_amount = slip.gross_amount + slip.reimbursement_amount + slip.employer_amount

    @api.ondelete(at_uninstall=False)
    def _unlink_except_approved(self):
        if any(slip.state in ('approved', 'paid') for slip in self):
            raise UserError(_('Payslips of approved or paid pay runs cannot be deleted.'))

    # ------------------------------------------------------------------
    # Computing
    # ------------------------------------------------------------------
    @api.model
    def _payroll_hours_source(self):
        source = self.env['ir.config_parameter'].sudo().get_param('advanced_payroll.hours_source') or 'standard'
        return source if hasattr(self, f'_payroll_hours_vals_{source}') else 'standard'

    @api.model
    def _payroll_auto_sources(self):
        """Line sources rebuilt on every compute."""
        return [key for key, _label in self.env['payroll.slip.line']._fields['source'].selection
                if key != 'manual']

    def action_compute(self):
        self.check_access('write')
        for slip in self:
            if slip.state != 'draft':
                raise UserError(_('%s is no longer a draft.', slip.name))
        self.sudo()._payroll_compute()
        return True

    def _payroll_compute(self):
        """Rebuild the automatic lines: pay for the period, then every payroll
        rule of the country in sequence. Entered lines are kept."""
        Line = self.env['payroll.slip.line'].sudo()
        for slip in self.filtered(lambda s: s.state == 'draft'):
            slip.line_ids.filtered(lambda l: l.source in slip._payroll_auto_sources()).unlink()
            Line.create([dict(vals, slip_id=slip.id) for vals in slip._payroll_pay_vals()])
            for rule in slip._payroll_rules():
                if not slip._payroll_rule_applies(rule):
                    continue
                vals = slip._payroll_rule_line_vals(rule)
                if vals and not slip.currency_id.is_zero(vals['amount']):
                    Line.create(dict(vals, slip_id=slip.id))
            slip.computed_date = fields.Datetime.now()

    def _payroll_pay_vals(self):
        """Lines paying the period: the salary, or for hourly employees the
        hours from Settings › Payroll › Pay Hours From."""
        self.ensure_one()
        profile = self.payroll_employee_id
        if profile.pay_basis == 'salary':
            return self._payroll_salary_vals()
        return getattr(self, f'_payroll_hours_vals_{self._payroll_hours_source()}')()

    def _payroll_period_share(self):
        """Share of a pay period the employee is paid for (starting or
        leaving part way through)."""
        self.ensure_one()
        profile = self.payroll_employee_id
        start = max(self.date_start, profile.date_start or self.date_start)
        end = min(self.date_end, profile.date_end or self.date_end)
        days = (self.date_end - self.date_start).days + 1
        return max((end - start).days + 1, 0) / days if days else 0.0

    def _payroll_standard_hours(self):
        self.ensure_one()
        profile = self.payroll_employee_id
        weeks = 52.0 / (self.pay_frequency_id.periods_per_year or 52)
        return profile.hours_per_week * weeks * self._payroll_period_share()

    def _payroll_salary_vals(self):
        self.ensure_one()
        profile = self.payroll_employee_id
        item = profile._ordinary_pay_item()
        amount = self.currency_id.round(
            profile.annual_salary / (self.pay_frequency_id.periods_per_year or 1) * self._payroll_period_share())
        hours = self._payroll_standard_hours()
        return [{
            'name': _('Salary'),
            'pay_item_id': item.id,
            'source': 'salary',
            'quantity': hours,
            'rate': amount / hours if hours else amount,
            'amount': amount,
        }]

    def _payroll_hours_vals_standard(self):
        self.ensure_one()
        profile = self.payroll_employee_id
        item = profile._ordinary_pay_item()
        return [self._payroll_hours_line_vals(item, self._payroll_standard_hours(), source='salary',
                                              name=_('Standard Hours'))]

    def _payroll_hours_line_vals(self, item, hours, source, name=None, multiplier=1.0):
        """Line paying ``hours`` of ``item`` at the employee's rate."""
        self.ensure_one()
        rate = self.payroll_employee_id._rate_for(item, multiplier)
        return {
            'name': name or item.name,
            'pay_item_id': item.id,
            'source': source,
            'quantity': hours,
            'rate': rate,
            'amount': self.currency_id.round(hours * rate),
        }

    # ------------------------------------------------------------------
    # Payroll rules. Country apps hook in through the methods below.
    # ------------------------------------------------------------------
    def _payroll_rules(self):
        self.ensure_one()
        return self.env['payroll.rule'].sudo().search([('country_id', '=', self.country_id.id)],
                                                      order='sequence, id')

    def _payroll_rule_applies(self, rule):
        """Whether ``rule`` applies to this payslip (e.g. a retirement
        contribution only for members)."""
        return True

    def _payroll_rule_rate(self, rule):
        """Rate (%) of a percentage rule for this employee."""
        return rule.rate

    def _payroll_tax_table(self, rule):
        """Tax table of a "Tax Table" rule for this employee (e.g. by tax code)."""
        return rule.tax_table_id

    def _payroll_tax_adjustments(self, rule):
        """Employee adjustments of a "Tax Table" rule: annual amounts added to
        income or taken off it, an annual credit taken off the tax, a credit
        base replacing the table's, and an extra amount withheld per period."""
        return {'annual_income': 0.0, 'annual_deduction': 0.0, 'annual_credit': 0.0,
                'credit_base': None, 'period_extra': 0.0}

    def _payroll_rule_base(self, rule):
        """The pay ``rule`` works from, from the lines so far."""
        self.ensure_one()
        lines = self.line_ids
        if rule.base == 'retirement':
            return sum(lines.filtered('retirement_eligible').mapped('amount'))
        if rule.base == 'gross':
            return sum(lines.filtered(lambda l: l.category in GROSS_CATEGORIES).mapped('amount'))
        return sum(lines.filtered('is_taxable').mapped('amount'))

    def _payroll_ytd_base(self, rule):
        """Pay ``rule`` already worked from earlier in the tax year."""
        self.ensure_one()
        year_start = self.country_id._tax_year_start(self.date_start)
        lines = self.env['payroll.slip.line'].sudo().search([
            ('rule_id.code', '=', rule.code),
            ('slip_id.payroll_employee_id', '=', self.payroll_employee_id.id),
            ('slip_id.state', 'in', ('approved', 'paid')),
            ('slip_id.date_start', '>=', year_start),
            ('slip_id.date_start', '<', self.date_start),
        ])
        return sum(lines.mapped('base_amount'))

    def _payroll_rule_line_vals(self, rule):
        self.ensure_one()
        periods = self.pay_frequency_id.periods_per_year or 1
        base = max(self._payroll_rule_base(rule) - rule.annual_exemption / periods, 0.0)
        amount, rate, quantity = getattr(self, f'_payroll_compute_{rule.compute_method}')(rule, base)
        return {
            'name': rule.name,
            'rule_id': rule.id,
            'source': 'rule',
            'base_amount': base,
            'quantity': quantity,
            'rate': rate,
            'amount': self.currency_id.round(amount),
        }

    def _payroll_compute_percentage(self, rule, base):
        """``rate`` % of the pay (less its share of the annual exemption)
        between the annual threshold and the annual maximum, counted year to
        date."""
        before = self._payroll_ytd_base(rule) if (rule.annual_threshold or rule.annual_cap) else 0.0

        def in_band(total):
            top = min(total, rule.annual_cap) if rule.annual_cap else total
            return max(top - rule.annual_threshold, 0.0)

        if rule.annual_threshold or rule.annual_cap:
            base = in_band(before + base) - in_band(before)
        rate = self._payroll_rule_rate(rule)
        return base * rate / 100.0, rate, base

    def _payroll_compute_brackets(self, rule, base):
        """Annualise the pay, apply the tax table and spread the tax back over
        the year's pay periods."""
        table = self._payroll_tax_table(rule)
        if not table:
            raise UserError(_('The payroll rule %s needs a tax table.', rule.name))
        periods = self.pay_frequency_id.periods_per_year or 1
        adjust = self._payroll_tax_adjustments(rule)
        annual = base * periods + adjust['annual_income'] - adjust['annual_deduction']
        tax = table._annual_tax(annual, credit_base=adjust['credit_base'])
        tax = max(tax - adjust['annual_credit'], 0.0) / periods + adjust['period_extra']
        return tax, base and tax / base * 100.0, base

    def _payroll_compute_fixed(self, rule, base):
        return rule.fixed_amount, 0.0, 1.0

    # ------------------------------------------------------------------
    # Year to date (payslip PDF)
    # ------------------------------------------------------------------
    def _payroll_ytd_slips(self):
        self.ensure_one()
        year_start = self.country_id._tax_year_start(self.date_start)
        return self.sudo().search([
            ('payroll_employee_id', '=', self.payroll_employee_id.id),
            ('state', 'in', ('approved', 'paid')),
            ('date_start', '>=', year_start),
            ('date_start', '<=', self.date_start),
        ]) | self

    def _payroll_ytd(self):
        """Year-to-date totals for the payslip PDF."""
        self.ensure_one()
        slips = self._payroll_ytd_slips()
        return {name: sum(slips.mapped(name)) for name in (
            'gross_amount', 'tax_amount', 'deduction_amount', 'reimbursement_amount', 'net_amount',
            'employer_amount')}

    def _payroll_next_period_start(self):
        self.ensure_one()
        return self.date_end + timedelta(days=1)


class PayrollSlipLine(models.Model):
    _name = 'payroll.slip.line'
    _description = 'Payslip Line'
    _order = 'slip_id, category_sequence, sequence, id'

    slip_id = fields.Many2one('payroll.slip', string='Payslip', required=True, index=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Description', required=True)
    pay_item_id = fields.Many2one('payroll.pay.item', string='Pay Item', index=True,
                                  domain="['|', ('country_id', '=', False), ('country_id', '=', country_id)]")
    rule_id = fields.Many2one('payroll.rule', string='Payroll Rule', index=True, readonly=True)
    code = fields.Char(string='Code', compute='_compute_from_source', store=True)
    category = fields.Selection(CATEGORIES, string='Category', compute='_compute_from_source', store=True,
                                readonly=False, precompute=True, required=True)
    category_sequence = fields.Integer(compute='_compute_from_source', store=True)
    calculation = fields.Selection(related='pay_item_id.calculation')
    is_taxable = fields.Boolean(string='Taxable', compute='_compute_from_source', store=True, readonly=False,
                                precompute=True)
    retirement_eligible = fields.Boolean(string='Retirement Contributions', compute='_compute_from_source',
                                         store=True, readonly=False, precompute=True)
    source = fields.Selection(LINE_SOURCES, string='From', required=True, default='manual', readonly=True)
    quantity = fields.Float(string='Quantity', default=1.0, help='Hours, or the pay a rule worked from.')
    rate = fields.Float(string='Rate', digits=(16, 4))
    amount = fields.Monetary(string='Amount', required=True, default=0.0)
    base_amount = fields.Monetary(string='Based On', readonly=True,
                                  help='Pay the rule worked from (kept for year-to-date thresholds and caps).')
    currency_id = fields.Many2one(related='slip_id.currency_id')
    country_id = fields.Many2one(related='slip_id.country_id')
    company_id = fields.Many2one(related='slip_id.company_id', store=True, index=True)
    state = fields.Selection(related='slip_id.state')
    is_deducted = fields.Boolean(compute='_compute_is_deducted')

    @api.depends('pay_item_id', 'rule_id')
    def _compute_from_source(self):
        order = {key: index for index, (key, _label) in enumerate(CATEGORIES)}
        for line in self:
            if line.rule_id:
                line.code = line.rule_id.code
                line.category = line.rule_id.category
                line.is_taxable = line.retirement_eligible = False
            elif line.pay_item_id:
                line.code = line.pay_item_id.code
                line.category = line.pay_item_id.category
                line.is_taxable = line.pay_item_id.is_taxable
                line.retirement_eligible = line.pay_item_id.retirement_eligible
            else:
                line.code = False
                line.category = line.category or 'earning'
            line.category_sequence = order.get(line.category, 99)

    def _compute_is_deducted(self):
        for line in self:
            line.is_deducted = line.category in DEDUCTED_CATEGORIES

    @api.onchange('pay_item_id')
    def _onchange_pay_item_id(self):
        item = self.pay_item_id
        if item:
            self.name = item.name
            profile = self.slip_id.payroll_employee_id
            self.rate = profile._rate_for(item) if item.calculation == 'hours' else self.rate
            if item.calculation == 'amount':
                self.quantity = 1.0

    @api.onchange('quantity', 'rate')
    def _onchange_quantity_rate(self):
        if not self.rule_id:
            self.amount = self.currency_id.round(self.quantity * self.rate) if self.currency_id else self.quantity * self.rate

    def _check_editable(self):
        if any(line.slip_id.state != 'draft' for line in self):
            raise UserError(_('Lines of approved, paid or cancelled payslips cannot be changed.'))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_editable()
        return lines

    def write(self, vals):
        self._check_editable()
        return super().write(vals)

    def unlink(self):
        self._check_editable()
        return super().unlink()

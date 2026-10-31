# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

RUN_STATES = [
    ('draft', 'Draft'),
    ('approved', 'Approved'),
    ('paid', 'Paid'),
    ('cancelled', 'Cancelled'),
]


class PayrollRun(models.Model):
    _name = 'payroll.run'
    _description = 'Pay Run'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    reference = fields.Char(string='Reference', readonly=True, copy=False, default=lambda self: _('New'))
    name = fields.Char(string='Pay Run', compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True, tracking=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    country_id = fields.Many2one(
        'payroll.country', string='Payroll Country', required=True, index=True, tracking=True,
        default=lambda self: self.env['payroll.country']._default_for_company(),
    )
    pay_frequency_id = fields.Many2one(
        'payroll.pay.frequency', string='Pay Frequency', required=True, tracking=True,
        compute='_compute_pay_frequency_id', store=True, readonly=False, precompute=True,
    )
    date_start = fields.Date(
        string='Period From', required=True, index=True, tracking=True, default=fields.Date.context_today,
        help='Pick any day: the pay run covers the whole pay period containing it.',
    )
    date_end = fields.Date(string='Period To', required=True, tracking=True,
                           compute='_compute_period', store=True, readonly=False, precompute=True)
    payment_date = fields.Date(string='Payment Date', required=True, tracking=True,
                               compute='_compute_payment_date', store=True, readonly=False, precompute=True)
    state = fields.Selection(RUN_STATES, string='Status', default='draft', required=True, readonly=True,
                             copy=False, tracking=True, index=True)
    slip_ids = fields.One2many('payroll.slip', 'run_id', string='Payslips', copy=False)
    slip_count = fields.Integer(compute='_compute_totals', string='Payslip Count')
    gross_amount = fields.Monetary(string='Gross Pay', compute='_compute_totals', store=True)
    tax_amount = fields.Monetary(string='Tax', compute='_compute_totals', store=True)
    net_amount = fields.Monetary(string='Net Pay', compute='_compute_totals', store=True)
    employer_amount = fields.Monetary(string='Employer Contributions', compute='_compute_totals', store=True)
    cost_amount = fields.Monetary(string='Employer Cost', compute='_compute_totals', store=True)
    approved_by_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)
    approved_date = fields.Datetime(string='Approved On', readonly=True, copy=False)
    paid_date = fields.Datetime(string='Marked Paid On', readonly=True, copy=False)
    note = fields.Html(string='Notes')

    @api.depends('reference', 'country_id', 'pay_frequency_id', 'date_start', 'date_end')
    def _compute_name(self):
        for run in self:
            dates = ' – '.join(d.strftime('%d/%m/%Y') for d in (run.date_start, run.date_end) if d)
            parts = [run.reference if run.reference != _('New') else False, run.country_id.name,
                     run.pay_frequency_id.name, dates]
            run.name = ' · '.join(part for part in parts if part) or _('New Pay Run')

    @api.depends('country_id')
    def _compute_pay_frequency_id(self):
        for run in self:
            if not run.pay_frequency_id:
                run.pay_frequency_id = run.country_id.default_pay_frequency_id

    @api.depends('date_start', 'pay_frequency_id')
    def _compute_period(self):
        for run in self:
            if run.date_start and run.pay_frequency_id:
                run.date_end = run.pay_frequency_id._period_bounds(run.date_start)[1]
            elif not run.date_end:
                run.date_end = run.date_start

    @api.depends('date_end')
    def _compute_payment_date(self):
        for run in self:
            run.payment_date = run.date_end

    @api.depends('slip_ids.gross_amount', 'slip_ids.tax_amount', 'slip_ids.net_amount',
                 'slip_ids.employer_amount', 'slip_ids.cost_amount')
    def _compute_totals(self):
        for run in self:
            slips = run.slip_ids
            run.slip_count = len(slips)
            run.gross_amount = sum(slips.mapped('gross_amount'))
            run.tax_amount = sum(slips.mapped('tax_amount'))
            run.net_amount = sum(slips.mapped('net_amount'))
            run.employer_amount = sum(slips.mapped('employer_amount'))
            run.cost_amount = sum(slips.mapped('cost_amount'))

    @api.onchange('date_start', 'pay_frequency_id')
    def _onchange_period(self):
        if self.date_start and self.pay_frequency_id:
            self.date_start, self.date_end = self.pay_frequency_id._period_bounds(self.date_start)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            frequency = self.env['payroll.pay.frequency'].browse(vals.get('pay_frequency_id'))
            if not frequency and vals.get('country_id'):
                frequency = self.env['payroll.country'].browse(vals['country_id']).default_pay_frequency_id
            if frequency and vals.get('date_start') and not vals.get('date_end'):
                start, end = frequency._period_bounds(fields.Date.to_date(vals['date_start']))
                vals.update(date_start=start, date_end=end)
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code('payroll.run') or _('New')
        return super().create(vals_list)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for run in self:
            if run.date_end < run.date_start:
                raise ValidationError(_('A pay run cannot end before it starts.'))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_approved(self):
        if any(run.state in ('approved', 'paid') for run in self):
            raise UserError(_('Approved and paid pay runs cannot be deleted. Reset them to draft first.'))

    # ------------------------------------------------------------------
    # Payslips
    # ------------------------------------------------------------------
    def _check_draft(self):
        for run in self:
            if run.state != 'draft':
                raise UserError(_('%s is no longer a draft. Reset it to draft to change it.', run.name))

    def _employee_domain(self):
        """Payroll profiles paid on this run."""
        self.ensure_one()
        return [
            ('company_id', '=', self.company_id.id),
            ('country_id', '=', self.country_id.id),
            ('pay_frequency_id', '=', self.pay_frequency_id.id),
            '|', ('date_start', '=', False), ('date_start', '<=', self.date_end),
            '|', ('date_end', '=', False), ('date_end', '>=', self.date_start),
        ]

    def action_generate_slips(self):
        """Add a payslip for everyone paid on this run who has none yet, and
        compute every payslip."""
        self.check_access('write')
        self._check_draft()
        Slip = self.env['payroll.slip'].sudo()
        for run in self:
            profiles = self.env['payroll.employee'].sudo().search(run._employee_domain())
            missing = profiles - run.slip_ids.payroll_employee_id
            if missing:
                Slip.create([{'run_id': run.id, 'payroll_employee_id': profile.id} for profile in missing])
            run.slip_ids.sudo()._payroll_compute()
            run.message_post(body=_('%(count)s payslips computed (%(new)s new).',
                                    count=len(run.slip_ids), new=len(missing)))
        return True

    def action_compute(self):
        self.check_access('write')
        self._check_draft()
        self.slip_ids.sudo()._payroll_compute()
        return True

    # ------------------------------------------------------------------
    # Workflow (each step is its own privilege; see CLAUDE.md > Permissions)
    # ------------------------------------------------------------------
    def _is_admin(self):
        return self.env.user.has_group('advanced_payroll.group_payroll_admin')

    def action_approve(self):
        if not self.env.user.has_group('advanced_payroll.group_run_approve'):
            raise AccessError(_('You need the Pay Runs: Approve permission to approve pay runs.'))
        self._check_draft()
        for run in self:
            if not run.slip_ids:
                raise UserError(_('%s has no payslips to approve.', run.name))
            negative = run.slip_ids.filtered(lambda s: s.net_amount < 0)
            if negative:
                raise UserError(_('These payslips have a negative net pay: %s', ', '.join(negative.mapped('name'))))
        self.sudo().write({'state': 'approved', 'approved_by_id': self.env.uid,
                           'approved_date': fields.Datetime.now()})
        self.sudo().slip_ids.write({'state': 'approved'})
        self._payroll_after_approve()
        for run in self:
            run.message_post(body=_('Pay run approved.'))
        return True

    def _payroll_after_approve(self):
        """Hook for integrations (e.g. the journal entry, advanced_payroll_accounting)."""

    def action_mark_paid(self):
        if not self.env.user.has_group('advanced_payroll.group_run_pay'):
            raise AccessError(_('You need the Pay Runs: Mark as Paid permission to mark pay runs as paid.'))
        for run in self:
            if run.state != 'approved':
                raise UserError(_('Only approved pay runs can be marked as paid.'))
        self.sudo().write({'state': 'paid', 'paid_date': fields.Datetime.now()})
        self.sudo().slip_ids.write({'state': 'paid'})
        self._payroll_after_paid()
        for run in self:
            run.message_post(body=_('Pay run marked as paid.'))
        return True

    def _payroll_after_paid(self):
        """Hook for integrations (e.g. the payment entry, advanced_payroll_accounting)."""

    def action_reset_to_draft(self):
        if not (self.env.user.has_group('advanced_payroll.group_run_approve') or self._is_admin()):
            raise AccessError(_('You need the Pay Runs: Approve permission to reset pay runs to draft.'))
        runs = self.filtered(lambda r: r.state != 'draft')
        if any(run.state == 'paid' for run in runs) and not self._is_admin():
            raise AccessError(_('Only a Payroll Administrator can reopen a paid pay run.'))
        runs._payroll_before_reset()
        runs.sudo().write({'state': 'draft', 'approved_by_id': False, 'approved_date': False, 'paid_date': False})
        runs.sudo().slip_ids.write({'state': 'draft'})
        for run in runs:
            run.message_post(body=_('Pay run reset to draft.'))
        return True

    def _payroll_before_reset(self):
        """Hook for integrations (e.g. reversing the journal entries)."""

    def action_cancel(self):
        self.check_access('write')
        self._check_draft()
        self.sudo().write({'state': 'cancelled'})
        self.sudo().slip_ids.write({'state': 'cancelled'})
        return True

    def action_open_slips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payslips'),
            'res_model': 'payroll.slip',
            'view_mode': 'list,form',
            'domain': [('run_id', '=', self.id)],
            'context': {'default_run_id': self.id},
        }

    def action_print_slips(self):
        return self.env.ref('advanced_payroll.action_report_payslip').report_action(self.slip_ids)

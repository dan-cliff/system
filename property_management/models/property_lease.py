# -*- coding: utf-8 -*-
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .property_property import LEASES_OUT

# Workflow state: code depends on these values (CLAUDE.md > Choice fields).
LEASE_STATES = [
    ('draft', 'Draft'),
    ('active', 'Active'),
    ('expired', 'Expired'),
    ('terminated', 'Terminated'),
]
# Which side of the lease the business is on: decides the totals, labels and
# defaults, so a fixed selection.
LEASE_TYPES = [
    ('in', 'We are the Tenant'),
    ('out', 'We are the Landlord'),
]


class PropertyLease(models.Model):
    _name = 'property.lease'
    _description = 'Property Lease'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(
        string='Reference', readonly=True, copy=False, default=lambda self: self.env._('New'), index='trigram')
    active = fields.Boolean(default=True)
    property_id = fields.Many2one(
        'property.property', string='Property', required=True, ondelete='restrict', index=True, tracking=True)
    lease_type = fields.Selection(
        LEASE_TYPES, string='Lease Type', required=True, tracking=True,
        compute='_compute_lease_type', store=True, readonly=False, precompute=True,
        help='We are the Tenant: we lease the premises from their owner.\n'
             'We are the Landlord: we lease our premises to someone else.',
    )
    state = fields.Selection(LEASE_STATES, default='draft', required=True, tracking=True, copy=False, index=True)
    user_id = fields.Many2one(
        'res.users', string='Responsible', default=lambda self: self.env.user, tracking=True, index=True,
        domain=[('share', '=', False)],
        help='Gets the reminders before the lease ends and before options must be exercised.',
    )
    company_id = fields.Many2one(
        'res.company', required=True, tracking=True, index=True,
        compute='_compute_company_id', store=True, readonly=False, precompute=True,
    )
    currency_id = fields.Many2one(
        'res.currency', required=True,
        compute='_compute_currency_id', store=True, readonly=False, precompute=True,
    )
    company_currency_id = fields.Many2one(related='company_id.currency_id', string='Company Currency')

    partner_id = fields.Many2one(
        'res.partner', string='Landlord / Tenant', tracking=True, ondelete='restrict', index=True,
        help='The other party to the lease: the landlord when we are the tenant, the tenant when we are '
             'the landlord.',
    )
    agent_id = fields.Many2one('res.partner', string='Agent', ondelete='restrict')
    premises = fields.Char(
        help='The part of the property the lease covers, e.g. "Suite 3, Level 1". Leave empty for the '
             'whole property.')
    permitted_use = fields.Char(string='Permitted Use')
    leased_area = fields.Float(string='Leased Area (m²)', digits=(16, 2))

    # Term
    date_signed = fields.Date(string='Signed On', tracking=True)
    date_start = fields.Date(string='Commences', required=True, tracking=True, default=fields.Date.context_today)
    date_end = fields.Date(string='Expires', tracking=True)
    term_months = fields.Integer(string='Term (Months)', compute='_compute_term', store=True)
    renewal_options = fields.Char(
        string='Options to Renew', help='e.g. "2 × 5 years".')
    option_notice_date = fields.Date(
        string='Exercise Options By', tracking=True,
        help='The last day to give notice that an option to renew is taken up. A reminder is scheduled '
             'before it.')
    notice_period_days = fields.Integer(string='Notice Period (Days)')
    break_clause = fields.Text(string='Break Clause')
    holding_over = fields.Text(string='Holding Over')
    previous_lease_id = fields.Many2one('property.lease', string='Renewal Of', copy=False, readonly=True)
    renewal_lease_ids = fields.One2many('property.lease', 'previous_lease_id', string='Renewals')
    renewal_lease_id = fields.Many2one(
        'property.lease', compute='_compute_renewal_lease_id', string='Renewed By')

    # Rent
    rent_amount = fields.Monetary(string='Rent', tracking=True, help='Rent per payment, before tax.')
    frequency_id = fields.Many2one(
        'property.rent.frequency', string='Paid', ondelete='restrict',
        default=lambda self: self.env.ref('property_management.rent_frequency_monthly', raise_if_not_found=False),
    )
    annual_rent = fields.Monetary(compute='_compute_annual_rent', store=True, string='Annual Rent')
    annual_rent_company = fields.Monetary(
        compute='_compute_annual_rent', store=True, string='Annual Rent (Company Currency)',
        currency_field='company_currency_id')
    rent_due_day = fields.Integer(string='Rent Due Day', help='Day of the month (or period) rent is due.')
    outgoings = fields.Monetary(string='Outgoings per Year', help='Rates, body corporate, building costs, …')
    outgoings_notes = fields.Text(string='Outgoings')
    bond_amount = fields.Monetary(string='Bond / Security Deposit')
    bond_reference = fields.Char(string='Bond Reference')
    bank_guarantee = fields.Boolean(string='Bank Guarantee')
    incentives = fields.Text()

    # Rent review
    review_type_id = fields.Many2one('property.rent.review.type', string='Rent Review', ondelete='restrict')
    review_rate = fields.Float(string='Review Rate (%)', digits=(16, 2))
    next_review_date = fields.Date(string='Next Review', tracking=True)
    review_notes = fields.Text(string='Review Notes')

    # Documents
    document = fields.Binary(string='Lease Document', attachment=True)
    document_name = fields.Char(string='Document File Name')
    notes = fields.Html()

    # Reminder bookkeeping (cron)
    reminder_end_sent = fields.Boolean(copy=False)
    reminder_option_sent = fields.Boolean(copy=False)
    reminder_review_sent = fields.Boolean(copy=False)
    days_to_expiry = fields.Integer(compute='_compute_days_to_expiry', string='Days to Expiry')
    is_expiring = fields.Boolean(
        compute='_compute_days_to_expiry', search='_search_is_expiring', string='Expiring Soon')

    @api.depends('property_id.ownership')
    def _compute_lease_type(self):
        for lease in self:
            if not lease.lease_type or lease._origin.property_id != lease.property_id:
                lease.lease_type = 'out' if lease.property_id.ownership in LEASES_OUT else 'in'

    @api.depends('property_id')
    def _compute_company_id(self):
        for lease in self:
            lease.company_id = lease.property_id.company_id or lease.company_id or self.env.company

    @api.depends('company_id')
    def _compute_currency_id(self):
        for lease in self:
            lease.currency_id = lease.currency_id or lease.company_id.currency_id or self.env.company.currency_id

    @api.depends('date_start', 'date_end')
    def _compute_term(self):
        for lease in self:
            if lease.date_start and lease.date_end and lease.date_end >= lease.date_start:
                delta = relativedelta(lease.date_end + timedelta(days=1), lease.date_start)
                lease.term_months = delta.years * 12 + delta.months
            else:
                lease.term_months = 0

    @api.depends('rent_amount', 'frequency_id.periods_per_year', 'currency_id', 'company_id', 'date_start')
    def _compute_annual_rent(self):
        for lease in self:
            annual = lease.rent_amount * (lease.frequency_id.periods_per_year or 0.0)
            lease.annual_rent = annual
            company_currency = lease.company_id.currency_id
            if lease.currency_id and company_currency and lease.currency_id != company_currency:
                annual = lease.currency_id._convert(
                    annual, company_currency, lease.company_id, lease.date_start or fields.Date.today())
            lease.annual_rent_company = annual

    @api.depends('renewal_lease_ids')
    def _compute_renewal_lease_id(self):
        for lease in self:
            lease.renewal_lease_id = lease.renewal_lease_ids[:1]

    @api.depends('date_end', 'state')
    @api.depends_context('uid')
    def _compute_days_to_expiry(self):
        today = fields.Date.context_today(self)
        horizon = self.env.company.property_reminder_days or 90
        for lease in self:
            days = (lease.date_end - today).days if lease.date_end else 0
            lease.days_to_expiry = days
            lease.is_expiring = bool(lease.state == 'active' and lease.date_end and days <= horizon)

    def _search_is_expiring(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        horizon = self.env.company.property_reminder_days or 90
        limit = fields.Date.context_today(self) + timedelta(days=horizon)
        domain = [('state', '=', 'active'), ('date_end', '!=', False), ('date_end', '<=', limit)]
        if (operator == '=') == value:
            return domain
        return ['!', '&', '&'] + domain

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for lease in self:
            if lease.date_start and lease.date_end and lease.date_end < lease.date_start:
                raise ValidationError(self.env._('A lease cannot expire before it commences.'))

    @api.constrains('property_id', 'company_id')
    def _check_company(self):
        for lease in self:
            if lease.property_id.company_id and lease.company_id != lease.property_id.company_id:
                raise ValidationError(self.env._("A lease must belong to its property's company."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == self.env._('New'):
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code(
                    'property.lease') or self.env._('New')
        return super().create(vals_list)

    def write(self, vals):
        # A moved date asks for a fresh reminder.
        if 'date_end' in vals:
            vals = dict(vals, reminder_end_sent=False)
        if 'option_notice_date' in vals:
            vals = dict(vals, reminder_option_sent=False)
        if 'next_review_date' in vals:
            vals = dict(vals, reminder_review_sent=False)
        return super().write(vals)

    @api.depends('name', 'property_id', 'partner_id')
    def _compute_display_name(self):
        for lease in self:
            parts = [lease.name, lease.property_id.name, lease.partner_id.name]
            lease.display_name = ' – '.join(p for p in parts if p)

    # ── Workflow ─────────────────────────────────────────────────────────

    def action_activate(self):
        for lease in self:
            if lease.state != 'draft':
                raise UserError(self.env._('Only draft leases can be made active.'))
        self.write({'state': 'active'})
        return True

    def action_terminate(self):
        self.filtered(lambda lease: lease.state == 'active').write({'state': 'terminated'})
        return True

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_renew(self):
        """A draft lease that carries on from this one."""
        self.ensure_one()
        if self.renewal_lease_id:
            raise UserError(self.env._('This lease has already been renewed by %s.', self.renewal_lease_id.name))
        start = (self.date_end + timedelta(days=1)) if self.date_end else fields.Date.context_today(self)
        end = False
        if self.date_start and self.date_end:
            end = start + relativedelta(self.date_end + timedelta(days=1), self.date_start) - timedelta(days=1)
        renewal = self.copy({
            'date_start': start,
            'date_end': end,
            'date_signed': False,
            'option_notice_date': False,
            'next_review_date': False,
            'document': False,
            'document_name': False,
            'previous_lease_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Lease Renewal'),
            'res_model': 'property.lease',
            'res_id': renewal.id,
            'view_mode': 'form',
        }

    # ── Scheduled job ────────────────────────────────────────────────────

    @api.model
    def _cron_lease_status_and_reminders(self):
        """Expire leases past their end date, and schedule To Do activities for
        the Responsible before a lease ends, before options must be exercised
        and before a rent review."""
        today = fields.Date.context_today(self)
        self.search([('state', '=', 'active'), ('date_end', '<', today)]).write({'state': 'expired'})
        for company in self.env['res.company'].search([]):
            horizon = today + timedelta(days=company.property_reminder_days or 90)
            base = [('company_id', '=', company.id), ('state', '=', 'active')]
            checks = (
                ('date_end', 'reminder_end_sent', self.env._('Lease ends on %s')),
                ('option_notice_date', 'reminder_option_sent', self.env._('Options to renew must be exercised by %s')),
                ('next_review_date', 'reminder_review_sent', self.env._('Rent review due on %s')),
            )
            for date_field, flag, summary in checks:
                leases = self.search(base + [(date_field, '!=', False), (date_field, '<=', horizon),
                                             (date_field, '>=', today), (flag, '=', False)])
                for lease in leases:
                    lease._property_schedule_reminder(summary % lease[date_field].strftime('%d/%m/%Y'),
                                                      lease[date_field])
                leases.write({flag: True})

    def _property_schedule_reminder(self, summary, deadline):
        self.ensure_one()
        user = self.user_id or self.property_id.user_id or self.create_uid
        self.activity_schedule(
            'mail.mail_activity_data_todo', date_deadline=deadline, summary=summary, user_id=user.id)

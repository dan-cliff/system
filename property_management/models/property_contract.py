# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Workflow state: code depends on these values (CLAUDE.md > Choice fields).
CONTRACT_STATES = [
    ('draft', 'Draft'),
    ('active', 'Active'),
    ('expired', 'Expired'),
    ('cancelled', 'Cancelled'),
]


class PropertyContract(models.Model):
    """Contracts for a property other than its leases: insurance, cleaning,
    security, maintenance, utilities, property management, …"""
    _name = 'property.contract'
    _description = 'Property Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_end, id desc'

    name = fields.Char(required=True, tracking=True)
    reference = fields.Char(string='Contract Number', tracking=True)
    active = fields.Boolean(default=True)
    property_id = fields.Many2one(
        'property.property', string='Property', required=True, ondelete='restrict', index=True, tracking=True)
    contract_type_id = fields.Many2one(
        'property.contract.type', string='Contract Type', ondelete='restrict', tracking=True)
    state = fields.Selection(CONTRACT_STATES, default='draft', required=True, tracking=True, copy=False, index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Supplier', tracking=True, ondelete='restrict', index=True,
        help='The other party to the contract: the insurer, contractor, utility provider, …')
    user_id = fields.Many2one(
        'res.users', string='Responsible', default=lambda self: self.env.user, tracking=True, index=True,
        domain=[('share', '=', False)], help='Gets the reminder before the contract ends.')
    company_id = fields.Many2one(
        'res.company', required=True, tracking=True, index=True,
        compute='_compute_company_id', store=True, readonly=False, precompute=True,
    )
    currency_id = fields.Many2one(
        'res.currency', required=True,
        compute='_compute_currency_id', store=True, readonly=False, precompute=True,
    )
    company_currency_id = fields.Many2one(related='company_id.currency_id', string='Company Currency')

    date_start = fields.Date(string='Starts', tracking=True, default=fields.Date.context_today)
    date_end = fields.Date(string='Ends', tracking=True)
    auto_renew = fields.Boolean(string='Renews Automatically')
    notice_period_days = fields.Integer(string='Notice Period (Days)')
    amount = fields.Monetary(string='Cost', tracking=True, help='Cost per payment, before tax.')
    frequency_id = fields.Many2one(
        'property.rent.frequency', string='Paid', ondelete='restrict',
        default=lambda self: self.env.ref('property_management.rent_frequency_annually', raise_if_not_found=False),
    )
    annual_amount = fields.Monetary(compute='_compute_annual_amount', store=True, string='Annual Cost')
    annual_amount_company = fields.Monetary(
        compute='_compute_annual_amount', store=True, string='Annual Cost (Company Currency)',
        currency_field='company_currency_id')
    sum_insured = fields.Monetary(string='Sum Insured', help='For insurance policies.')
    document = fields.Binary(string='Contract Document', attachment=True)
    document_name = fields.Char(string='Document File Name')
    description = fields.Html()
    reminder_end_sent = fields.Boolean(copy=False)

    @api.depends('property_id')
    def _compute_company_id(self):
        for contract in self:
            contract.company_id = contract.property_id.company_id or contract.company_id or self.env.company

    @api.depends('company_id')
    def _compute_currency_id(self):
        for contract in self:
            contract.currency_id = (contract.currency_id or contract.company_id.currency_id
                                    or self.env.company.currency_id)

    @api.depends('amount', 'frequency_id.periods_per_year', 'currency_id', 'company_id', 'date_start')
    def _compute_annual_amount(self):
        for contract in self:
            annual = contract.amount * (contract.frequency_id.periods_per_year or 0.0)
            contract.annual_amount = annual
            company_currency = contract.company_id.currency_id
            if contract.currency_id and company_currency and contract.currency_id != company_currency:
                annual = contract.currency_id._convert(
                    annual, company_currency, contract.company_id, contract.date_start or fields.Date.today())
            contract.annual_amount_company = annual

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for contract in self:
            if contract.date_start and contract.date_end and contract.date_end < contract.date_start:
                raise ValidationError(self.env._('A contract cannot end before it starts.'))

    @api.constrains('property_id', 'company_id')
    def _check_company(self):
        for contract in self:
            if contract.property_id.company_id and contract.company_id != contract.property_id.company_id:
                raise ValidationError(self.env._("A contract must belong to its property's company."))

    def write(self, vals):
        if 'date_end' in vals:
            vals = dict(vals, reminder_end_sent=False)
        return super().write(vals)

    def action_activate(self):
        self.filtered(lambda c: c.state == 'draft').write({'state': 'active'})
        return True

    def action_cancel(self):
        self.filtered(lambda c: c.state in ('draft', 'active')).write({'state': 'cancelled'})
        return True

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        return True

    @api.model
    def _cron_contract_status_and_reminders(self):
        """Expire contracts past their end date (unless they renew
        automatically) and remind the Responsible before they end."""
        today = fields.Date.context_today(self)
        self.search([('state', '=', 'active'), ('auto_renew', '=', False),
                     ('date_end', '<', today)]).write({'state': 'expired'})
        for company in self.env['res.company'].search([]):
            horizon = today + timedelta(days=company.property_reminder_days or 90)
            contracts = self.search([
                ('company_id', '=', company.id), ('state', '=', 'active'), ('date_end', '!=', False),
                ('date_end', '<=', horizon), ('date_end', '>=', today), ('reminder_end_sent', '=', False)])
            for contract in contracts:
                user = contract.user_id or contract.property_id.user_id or contract.create_uid
                contract.activity_schedule(
                    'mail.mail_activity_data_todo', date_deadline=contract.date_end, user_id=user.id,
                    summary=self.env._('Contract ends on %s', contract.date_end.strftime('%d/%m/%Y')))
            contracts.write({'reminder_end_sent': True})

"""Subscriptions: customers billed on a schedule.

A subscription holds the products a customer pays for again and again and the
template that says how often (every N days, weeks, months or years), for how
long (forever, or a fixed number of periods) and how it is billed (a draft
invoice, a posted invoice, a posted invoice emailed to the customer, or a sales
order and its invoice). A scheduled action raises the invoices when they are
due, starts the subscriptions whose start date has come and closes the ones that
have run their course.

The models, fields and external IDs are those of the Subscription management
app (subscription_oca), which Accounting takes over (see hooks.py): the
subscriptions it holds stay as they are.

Stages carry a technical type the code relies on: Draft, Ready to start
(started by the scheduled action on its start date), In progress (invoiced) and
Closed.
"""
import logging
from datetime import date, datetime

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return fields.Date.to_date(value)


class SaleSubscription(models.Model):
    _name = 'sale.subscription'
    _description = 'Subscription'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True
    # Organisation: a subscription made from a sales order follows the order
    _org_parent_field = 'sale_order_id'

    name = fields.Char(compute='_compute_name', store=True)
    code = fields.Char(string='Reference', copy=False, tracking=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('sale.subscription'))
    sequence = fields.Integer()
    color = fields.Integer('Color Index')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True,
                                 default=lambda self: self.env.company, tracking=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, index=True,
                                 check_company=True, tracking=True)
    partner_invoice_id = fields.Many2one(
        'res.partner', string='Invoice Address', check_company=True,
        compute='_compute_partner_address_ids', store=True, readonly=False,
        help="Where the invoices are addressed. Defaults to the customer's invoice address.")
    partner_shipping_id = fields.Many2one(
        'res.partner', string='Delivery Address', check_company=True,
        compute='_compute_partner_address_ids', store=True, readonly=False,
        help="The delivery address of the invoices and orders. Defaults to the customer's delivery address.")
    user_id = fields.Many2one('res.users', string='Salesperson', default=lambda self: self.env.user,
                              domain="[('share', '=', False)]", tracking=True)
    crm_team_id = fields.Many2one('crm.team', string='Sales Team', check_company=True)
    tag_ids = fields.Many2many('sale.subscription.tag', string='Tags')

    template_id = fields.Many2one('sale.subscription.template', string='Subscription Template',
                                  required=True, tracking=True)
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', check_company=True,
                                   compute='_compute_pricelist_id', store=True, readonly=False)
    currency_id = fields.Many2one('res.currency', string='Currency', compute='_compute_currency_id',
                                  store=True, ondelete='restrict')
    fiscal_position_id = fields.Many2one('account.fiscal.position', string='Fiscal Position', check_company=True,
                                         compute='_compute_fiscal_position_id', store=True, readonly=False)
    journal_id = fields.Many2one('account.journal', string='Invoice Journal', check_company=True,
                                 domain="[('type', '=', 'sale')]",
                                 help="The journal of the invoices. Leave empty for the default sales journal.")

    stage_id = fields.Many2one('sale.subscription.stage', string='Stage', tracking=True, index=True,
                               copy=False, default=lambda self: self._default_stage_id(),
                               group_expand='_read_group_stage_ids')
    stage_type = fields.Selection(related='stage_id.type', string='Stage Type')
    in_progress = fields.Boolean(string='In Progress', copy=False,
                                 help="Set while the subscription is in an In progress stage: it is then invoiced.")
    is_paused = fields.Boolean(string='Paused', tracking=True, copy=False, index='btree_not_null',
                               help="A paused subscription is not invoiced until it is resumed, by hand or on its "
                                    "resume date.")
    paused_until = fields.Date(string='Resume On', tracking=True, copy=False,
                               help="The day the scheduled action resumes the subscription. Leave empty to pause it "
                                    "until it is resumed by hand.")
    close_reason_id = fields.Many2one('sale.subscription.close.reason', string='Close Reason', copy=False,
                                      tracking=True)
    to_renew = fields.Boolean(string='To Renew', tracking=True)

    date_start = fields.Date(string='Start Date', default=fields.Date.context_today, tracking=True)
    recurring_next_date = fields.Date(string='Next Invoice Date', default=fields.Date.context_today,
                                      copy=False, tracking=True)
    recurring_rule_boundary = fields.Boolean(
        string='Runs Forever', compute='_compute_rule_boundary', store=True,
        help="Set when the template has no end: the subscription then runs until it is closed.")
    date = fields.Date(string='End Date', compute='_compute_rule_boundary', store=True, readonly=False,
                       tracking=True,
                       help="The subscription is closed on this day. Empty for a subscription that runs forever.")

    sale_subscription_line_ids = fields.One2many('sale.subscription.line', 'sale_subscription_id',
                                                 string='Products', copy=True)
    recurring_total = fields.Monetary(string='Recurring Price', compute='_compute_total', store=True)
    amount_tax = fields.Monetary(string='Taxes', compute='_compute_total', store=True)
    amount_total = fields.Monetary(string='Total', compute='_compute_total', store=True)

    description = fields.Text(string='Internal Notes')
    terms = fields.Text(string='Terms and Conditions', compute='_compute_terms', store=True, readonly=False)

    sale_order_id = fields.Many2one('sale.order', string='Origin Sales Order', copy=False, index='btree_not_null',
                                    check_company=True)
    sale_order_ids = fields.One2many('sale.order', 'order_subscription_id', string='Orders')
    invoice_ids = fields.One2many('account.move', 'subscription_id', string='Invoices')
    sale_order_ids_count = fields.Integer(string='Sales Orders', compute='_compute_sale_order_ids_count')
    account_invoice_ids_count = fields.Integer(string='Invoice Count', compute='_compute_account_invoice_ids_count')

    # ------------------------------------------------------------------
    # Defaults and computes
    # ------------------------------------------------------------------

    @api.model
    def _default_stage_id(self):
        Stage = self.env['sale.subscription.stage']
        return Stage.search([('type', '=', 'draft')], limit=1) or Stage.search([('type', '=', 'pre')], limit=1)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([], order=stages._order)

    @api.depends('template_id.code', 'code')
    def _compute_name(self):
        for sub in self:
            sub.name = '/'.join(part for part in (sub.template_id.code, sub.code) if part) or False

    @api.depends('partner_id')
    def _compute_partner_address_ids(self):
        for sub in self:
            addresses = sub.partner_id.address_get(['invoice', 'delivery']) if sub.partner_id else {}
            sub.partner_invoice_id = addresses.get('invoice', False)
            sub.partner_shipping_id = addresses.get('delivery', False)

    @api.depends('partner_id', 'company_id')
    def _compute_pricelist_id(self):
        for sub in self:
            if sub.partner_id:
                sub.pricelist_id = sub.partner_id.with_company(sub.company_id).property_product_pricelist

    @api.depends('pricelist_id', 'company_id')
    def _compute_currency_id(self):
        for sub in self:
            sub.currency_id = sub.pricelist_id.currency_id or sub.company_id.currency_id or self.env.company.currency_id

    @api.depends('partner_id', 'company_id')
    def _compute_fiscal_position_id(self):
        for sub in self:
            sub.fiscal_position_id = self.env['account.fiscal.position'].with_company(
                sub.company_id)._get_fiscal_position(sub.partner_id) if sub.partner_id else False

    @api.depends('template_id.recurring_rule_boundary', 'template_id.recurring_rule_type',
                 'template_id.recurring_interval', 'template_id.recurring_rule_count', 'date_start')
    def _compute_rule_boundary(self):
        for sub in self:
            template = sub.template_id
            if not template or template.recurring_rule_boundary != 'limited':
                sub.recurring_rule_boundary = True
                sub.date = False
            else:
                sub.recurring_rule_boundary = False
                sub.date = template._get_date(sub.date_start) if sub.date_start else False

    @api.depends('template_id')
    def _compute_terms(self):
        for sub in self:
            sub.terms = sub.template_id.description

    @api.depends('sale_subscription_line_ids.price_subtotal', 'sale_subscription_line_ids.amount_tax_line_amount')
    def _compute_total(self):
        for sub in self:
            untaxed = sum(sub.sale_subscription_line_ids.mapped('price_subtotal'))
            tax = sum(sub.sale_subscription_line_ids.mapped('amount_tax_line_amount'))
            sub.recurring_total = untaxed
            sub.amount_tax = tax
            sub.amount_total = untaxed + tax

    def _compute_sale_order_ids_count(self):
        counts = dict(self.env['sale.order'].sudo()._read_group(
            [('order_subscription_id', 'in', self.ids)], ['order_subscription_id'], ['__count']))
        for sub in self:
            sub.sale_order_ids_count = counts.get(sub._origin, 0)

    def _get_invoices(self):
        return self.invoice_ids | self.sale_order_ids.invoice_ids

    @api.depends('invoice_ids', 'sale_order_ids.invoice_ids')
    def _compute_account_invoice_ids_count(self):
        for sub in self:
            sub.account_invoice_ids_count = len(sub.sudo()._get_invoices())

    @api.onchange('template_id', 'date_start')
    def _onchange_template_id(self):
        """ Until it has been invoiced, a subscription is first invoiced on its start date. """
        if self.date_start and not self.account_invoice_ids_count:
            self.recurring_next_date = self.date_start

    # ------------------------------------------------------------------
    # Dates
    # ------------------------------------------------------------------

    def _get_recurrence_delta(self, periods=1):
        self.ensure_one()
        template = self.template_id
        return relativedelta(**{template.recurring_rule_type or 'months': (template.recurring_interval or 1) * periods})

    def _get_next_invoice_date(self, previous_date):
        return _to_date(previous_date) + self._get_recurrence_delta()

    def _advance_next_invoice_date(self):
        """ After an invoice, the next one falls one period later. """
        for sub in self:
            previous = sub.recurring_next_date or sub.date_start or fields.Date.context_today(sub)
            sub.recurring_next_date = sub._get_next_invoice_date(previous)

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------

    def _stage_values(self, stage):
        """ What changes with a move to `stage`, for this subscription. """
        self.ensure_one()
        today = fields.Date.context_today(self)
        if stage.type == 'in_progress':
            values = {'in_progress': True}
            if not self.in_progress:
                values['close_reason_id'] = False
                start = self.date_start if self.date_start and self.date_start <= today else today
                values['date_start'] = start
                if not self.account_invoice_ids_count:
                    values['recurring_next_date'] = start
            return values
        if stage.type == 'post':
            return {'in_progress': False, 'recurring_next_date': False}
        return {'in_progress': False}

    def write(self, vals):
        if 'stage_id' not in vals:
            return super().write(vals)
        stage = self.env['sale.subscription.stage'].browse(vals['stage_id'])
        for sub in self:
            values = dict(vals)
            if stage:
                values = {**sub._stage_values(stage), **values}
            super(SaleSubscription, sub).write(values)
        return True

    def action_start_subscription(self):
        stage = self.env['sale.subscription.stage'].search([('type', '=', 'in_progress')], limit=1)
        if not stage:
            raise UserError(self.env._('Add an "In progress" stage in Configuration › Subscription Stages first.'))
        self.write({'stage_id': stage.id, 'close_reason_id': False})

    def close_subscription(self, close_reason_id=False):
        stage = self.env['sale.subscription.stage'].search([('type', '=', 'post')], limit=1)
        if not stage:
            raise UserError(self.env._('Add a "Closed" stage in Configuration › Subscription Stages first.'))
        self.write({'stage_id': stage.id, 'close_reason_id': close_reason_id or False})

    def action_close_subscription(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Close Subscription'),
            'res_model': 'close.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id, 'active_model': self._name},
        }

    # ------------------------------------------------------------------
    # Pausing
    # ------------------------------------------------------------------

    def action_open_pause_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Pause Subscription'),
            'res_model': 'sale.subscription.pause.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id, 'active_model': self._name},
        }

    def action_pause(self, paused_until=None):
        for sub in self:
            if sub.stage_type == 'post':
                raise UserError(self.env._('A closed subscription cannot be paused.'))
            if sub.is_paused:
                raise UserError(self.env._('%(name)s is already paused.', name=sub.display_name))
            sub.write({'is_paused': True, 'paused_until': paused_until or False})
            if paused_until:
                sub.message_post(body=self.env._('Subscription paused until %(date)s.',
                                                 date=_to_date(paused_until).strftime('%d/%m/%Y')))
            else:
                sub.message_post(body=self.env._('Subscription paused.'))

    def action_resume(self, automatic=False):
        for sub in self:
            if not sub.is_paused:
                raise UserError(self.env._('%(name)s is not paused.', name=sub.display_name))
            sub.write({'is_paused': False, 'paused_until': False})
            sub.message_post(body=self.env._('Subscription resumed automatically.') if automatic
                             else self.env._('Subscription resumed.'))

    # ------------------------------------------------------------------
    # Invoicing
    # ------------------------------------------------------------------

    def _prepare_account_move(self, line_commands):
        self.ensure_one()
        invoice_partner = self.partner_invoice_id or self.partner_id
        values = {
            'move_type': 'out_invoice',
            'company_id': self.company_id.id,
            'partner_id': invoice_partner.id,
            'partner_shipping_id': (self.partner_shipping_id or self.partner_id).id,
            'currency_id': self.currency_id.id,
            'fiscal_position_id': self.fiscal_position_id.id,
            'invoice_date': self.recurring_next_date or fields.Date.context_today(self),
            'invoice_payment_term_id': invoice_partner.property_payment_term_id.id,
            'invoice_origin': self.name,
            'invoice_user_id': self.user_id.id,
            'team_id': self.crm_team_id.id,
            'partner_bank_id': self.company_id.partner_id.bank_ids[:1].id,
            'narration': self.terms,
            'invoice_line_ids': line_commands,
            'subscription_id': self.id,
        }
        if self.journal_id:
            values['journal_id'] = self.journal_id.id
        return values

    def _prepare_sale_order(self, line_commands):
        self.ensure_one()
        return {
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'partner_invoice_id': (self.partner_invoice_id or self.partner_id).id,
            'partner_shipping_id': (self.partner_shipping_id or self.partner_id).id,
            'pricelist_id': self.pricelist_id.id,
            'fiscal_position_id': self.fiscal_position_id.id,
            'payment_term_id': self.partner_id.property_payment_term_id.id,
            'user_id': self.user_id.id,
            'team_id': self.crm_team_id.id,
            'origin': self.name,
            'order_subscription_id': self.id,
            'order_line': line_commands,
        }

    def create_invoice(self):
        """ The invoice of the current period, as a draft. """
        self.ensure_one()
        lines = [Command.create(line._prepare_account_move_line()) for line in self.sale_subscription_line_ids]
        return self.env['account.move'].sudo().with_company(self.company_id).with_context(
            default_move_type='out_invoice').create(self._prepare_account_move(lines))

    def create_sale_order(self):
        """ A sales order for the current period. """
        self.ensure_one()
        lines = [Command.create(line._prepare_sale_order_line()) for line in self.sale_subscription_line_ids]
        return self.env['sale.order'].sudo().with_company(self.company_id).create(self._prepare_sale_order(lines))

    def _invoice_link(self, invoice):
        return Markup('<a href="#" data-oe-model="account.move" data-oe-id="%s">%s</a>') % (
            invoice.id, invoice.name or self.env._('Draft Invoice'))

    def generate_invoice(self):
        """ Invoice the current period the way the template says, then move
        the next invoice date one period on. Returns the invoices. """
        invoices = self.env['account.move']
        for sub in self:
            mode = sub.template_id.invoicing_mode or 'draft'
            if mode == 'sale_and_invoice':
                order = sub.create_sale_order()
                order.action_confirm()
                order.action_lock()
                invoice = order._create_invoices()
                invoice.action_post()
                invoice.invoice_origin = '%s, %s' % (order.name, sub.name)
            else:
                invoice = sub.create_invoice()
                if mode in ('invoice', 'invoice_send'):
                    invoice.action_post()
                if mode == 'invoice_send':
                    self.env['account.move.send'].sudo()._generate_and_send_invoices(
                        invoice, mail_template=sub.template_id.invoice_mail_template_id or None,
                        sending_methods=['email'], allow_raising=False)
            sub._advance_next_invoice_date()
            sub.message_post(body=self.env._('Invoice created: %(invoice)s', invoice=sub._invoice_link(invoice)))
            invoices |= invoice
        return invoices

    def manual_invoice(self):
        """ The "Create Invoice" button: a draft invoice for the current
        period, opened for checking. """
        self.ensure_one()
        if not self.sale_subscription_line_ids:
            raise UserError(self.env._('Add the products of the subscription before invoicing it.'))
        invoice = self.create_invoice()
        self._advance_next_invoice_date()
        self.message_post(body=self.env._('Invoice created: %(invoice)s', invoice=self._invoice_link(invoice)))
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'views': [(self.env.ref('account.view_move_form').id, 'form')],
        }

    # ------------------------------------------------------------------
    # Scheduled action
    # ------------------------------------------------------------------

    @api.model
    def cron_subscription_management(self):
        """ Daily: resume the paused subscriptions whose resume date has come,
        start the ready ones whose start date has come, invoice the ones due
        and close the ones that have reached their end date. One failing
        subscription is logged and left for the next run. """
        today = fields.Date.context_today(self)
        for sub in self.search([('is_paused', '=', True), ('paused_until', '!=', False),
                                ('paused_until', '<=', today)]):
            self._cron_run(sub, lambda s: s.action_resume(automatic=True))

        def run(sub):
            if sub.is_paused:
                return
            if sub.stage_type == 'pre' and sub.date_start and sub.date_start <= today:
                sub.action_start_subscription()
            if not sub.in_progress:
                return
            if sub.recurring_next_date and sub.recurring_next_date <= today and sub.sale_subscription_line_ids:
                sub.generate_invoice()
            if not sub.recurring_rule_boundary and sub.date and sub.date <= today:
                sub.close_subscription()

        for sub in self.search(['|', ('in_progress', '=', True), ('stage_id.type', '=', 'pre')],
                               order='recurring_next_date asc, id'):
            self._cron_run(sub, run)

    @api.model
    def _cron_run(self, sub, job):
        try:
            with self.env.cr.savepoint():
                job(sub.with_company(sub.company_id))
        except Exception:
            _logger.exception('Subscriptions: could not process subscription %s', sub.id)

    # ------------------------------------------------------------------
    # Smart buttons
    # ------------------------------------------------------------------

    def action_view_account_invoice_ids(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_out_invoice_type')
        action.update({
            'name': self.env._('Invoices'),
            'domain': [('id', 'in', self._get_invoices().ids)],
            'context': {'create': False, 'default_move_type': 'out_invoice'},
        })
        return action

    def action_view_sale_order_ids(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Sales Orders'),
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.sale_order_ids.ids)],
            'context': {'create': False},
        }

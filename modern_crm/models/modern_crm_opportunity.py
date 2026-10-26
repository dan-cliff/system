from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

GROUP_QUOTE = 'modern_crm.group_modern_crm_quote_create'
GROUP_SALE_ORDER = 'modern_crm.group_modern_crm_sale_order'
GROUP_INVOICE = 'modern_crm.group_modern_crm_invoice'


class ModernCrmOpportunity(models.Model):
    _name = 'modern.crm.opportunity'
    _description = 'CRM Opportunity'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'utm.mixin']
    _order = 'close_date, id desc'
    _rec_names_search = ['name', 'partner_id.name']
    # Converted from a lead: the opportunity takes the lead's Organisation units.
    _org_parent_field = 'lead_id'

    def _default_stage_id(self):
        return self.env['modern.crm.stage'].search([('is_won', '=', False), ('is_lost', '=', False)], limit=1)

    def _default_close_date(self):
        return fields.Date.context_today(self) + timedelta(days=30)

    name = fields.Char('Opportunity Name', required=True, index='trigram', tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string='Account', tracking=True, index=True,
        help='The customer (company or person) this opportunity is with.')
    contact_id = fields.Many2one(
        'res.partner', string='Primary Contact', tracking=True,
        domain="[('id', 'child_of', partner_id)]")
    user_id = fields.Many2one(
        'res.users', string='Opportunity Owner', tracking=True, index=True,
        default=lambda self: self.env.user,
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]")
    team_id = fields.Many2one('crm.team', string='Sales Team', tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    stage_id = fields.Many2one(
        'modern.crm.stage', string='Stage', required=True, tracking=True, index=True, copy=False,
        ondelete='restrict', default=_default_stage_id, group_expand='_read_group_stage_ids')
    stage_guidance = fields.Html(related='stage_id.guidance')
    is_won = fields.Boolean(related='stage_id.is_won', store=True)
    is_lost = fields.Boolean(related='stage_id.is_lost', store=True)
    is_closed = fields.Boolean(compute='_compute_is_closed', store=True)
    probability = fields.Float(
        'Probability (%)', compute='_compute_probability', store=True, readonly=False,
        tracking=True, aggregator='avg')
    forecast_category_id = fields.Many2one(
        'modern.crm.forecast.category', string='Forecast Category',
        compute='_compute_forecast_category_id', store=True, readonly=False, tracking=True)
    amount = fields.Monetary(
        'Amount', currency_field='currency_id', compute='_compute_amount', store=True,
        readonly=False, tracking=True,
        help='Total of the products when the opportunity has any, otherwise entered by hand.')
    expected_revenue = fields.Monetary(
        'Expected Revenue', currency_field='currency_id', compute='_compute_expected_revenue',
        store=True)
    close_date = fields.Date('Close Date', required=True, tracking=True, default=_default_close_date)
    date_closed = fields.Datetime('Closed On', readonly=True, copy=False)
    next_step = fields.Char('Next Step', tracking=True)
    type_id = fields.Many2one('modern.crm.opportunity.type', string='Type', tracking=True)
    lead_source_id = fields.Many2one('modern.crm.lead.source', string='Lead Source')
    lead_id = fields.Many2one('modern.crm.lead', string='Converted From Lead', readonly=True, copy=False)
    lost_reason_id = fields.Many2one(
        'modern.crm.lost.reason', string='Lost Reason', tracking=True, copy=False)
    lost_note = fields.Text('Lost Notes', copy=False)
    description = fields.Html()
    color = fields.Integer('Color Index')
    line_ids = fields.One2many(
        'modern.crm.opportunity.line', 'opportunity_id', string='Products', copy=True)
    contact_role_ids = fields.One2many(
        'modern.crm.contact.role', 'opportunity_id', string='Contact Roles', copy=True)

    order_ids = fields.One2many('sale.order', 'modern_opportunity_id', string='Quotes and Orders')
    primary_quote_id = fields.Many2one(
        'sale.order', string='Primary Quote', copy=False, tracking=True,
        domain="[('modern_opportunity_id', '=', id)]",
        help='The quote this opportunity is working towards: Confirm Sale turns it into a sales order.')
    primary_quote_state = fields.Selection(related='primary_quote_id.state', string='Primary Quote Status')
    quotation_count = fields.Integer(compute='_compute_sale_data')
    sale_order_count = fields.Integer(compute='_compute_sale_data')
    invoice_count = fields.Integer(compute='_compute_sale_data')
    sale_amount_total = fields.Monetary(
        'Sold', compute='_compute_sale_data', currency_field='currency_id')
    can_invoice = fields.Boolean(compute='_compute_sale_data')

    @api.depends('is_won', 'is_lost')
    def _compute_is_closed(self):
        for opportunity in self:
            opportunity.is_closed = opportunity.is_won or opportunity.is_lost

    @api.depends('stage_id')
    def _compute_probability(self):
        for opportunity in self:
            if opportunity.stage_id.is_won:
                opportunity.probability = 100.0
            elif opportunity.stage_id.is_lost:
                opportunity.probability = 0.0
            else:
                opportunity.probability = opportunity.stage_id.probability

    @api.depends('stage_id')
    def _compute_forecast_category_id(self):
        for opportunity in self:
            if opportunity.stage_id.forecast_category_id:
                opportunity.forecast_category_id = opportunity.stage_id.forecast_category_id

    @api.depends('line_ids.price_subtotal')
    def _compute_amount(self):
        for opportunity in self:
            if opportunity.line_ids:
                opportunity.amount = sum(opportunity.line_ids.mapped('price_subtotal'))

    @api.depends('amount', 'probability')
    def _compute_expected_revenue(self):
        for opportunity in self:
            opportunity.expected_revenue = opportunity.amount * opportunity.probability / 100.0

    @api.depends('order_ids.state', 'order_ids.invoice_ids', 'order_ids.invoice_status')
    def _compute_sale_data(self):
        # Sales documents follow Sales/Accounting access, which CRM users may not
        # have: count them as superuser, the buttons check access when opened.
        for opportunity in self:
            orders = opportunity.sudo().order_ids
            confirmed = orders.filtered(lambda o: o.state == 'sale')
            opportunity.quotation_count = len(orders.filtered(lambda o: o.state in ('draft', 'sent')))
            opportunity.sale_order_count = len(confirmed)
            opportunity.invoice_count = len(confirmed.invoice_ids)
            opportunity.sale_amount_total = sum(
                o.currency_id._convert(o.amount_untaxed, opportunity.currency_id, o.company_id, o.date_order)
                for o in confirmed)
            opportunity.can_invoice = any(o.invoice_status == 'to invoice' for o in confirmed)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([])

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.contact_id and self.partner_id and self.contact_id.commercial_partner_id != self.partner_id.commercial_partner_id:
            self.contact_id = False
        if self.partner_id and not self.partner_id.is_company and not self.contact_id:
            self.contact_id = self.partner_id

    @api.model_create_multi
    def create(self, vals_list):
        opportunities = super().create(vals_list)
        opportunities.filtered('is_closed').date_closed = fields.Datetime.now()
        return opportunities

    def write(self, vals):
        if 'stage_id' in vals:
            stage = self.env['modern.crm.stage'].browse(vals['stage_id'])
            if stage.is_won or stage.is_lost:
                vals.setdefault('date_closed', fields.Datetime.now())
            else:
                vals.update(date_closed=False)
            if not stage.is_lost:
                vals.update(lost_reason_id=False, lost_note=False)
        return super().write(vals)

    # ------------------------------------------------------------------
    # Closing
    # ------------------------------------------------------------------
    def _closing_stage(self, won):
        stage = self.env['modern.crm.stage'].search([('is_won' if won else 'is_lost', '=', True)], limit=1)
        if not stage:
            raise UserError(self.env._('Add a stage marked "%s" under CRM > Configuration > Stages first.',
                                       self.env._('Closed Won') if won else self.env._('Closed Lost')))
        return stage

    def action_set_won(self):
        self.filtered(lambda o: not o.is_won).write({'stage_id': self._closing_stage(won=True).id})
        return True

    def action_set_lost(self):
        return {
            'name': self.env._('Close as Lost'),
            'type': 'ir.actions.act_window',
            'res_model': 'modern.crm.reason.wizard',
            'view_mode': 'form',
            'views': [(self.env.ref('modern_crm.modern_crm_reason_wizard_view_form_lost').id, 'form')],
            'target': 'new',
            'context': {'default_opportunity_ids': self.ids, 'default_mode': 'lost'},
        }

    def _action_set_lost(self, reason, note=False):
        self.write({'stage_id': self._closing_stage(won=False).id,
                    'lost_reason_id': reason.id, 'lost_note': note})

    def action_reopen(self):
        stage = self.env['modern.crm.stage'].search([('is_won', '=', False), ('is_lost', '=', False)], limit=1)
        self.filtered('is_closed').write({'stage_id': stage.id})
        return True

    # ------------------------------------------------------------------
    # Quotes, sales orders and invoices
    # ------------------------------------------------------------------
    def _check_workflow_group(self, group, action):
        if not self.env.user.has_group(group):
            raise AccessError(self.env._('You are not allowed to %s. Ask your CRM administrator for the permission.', action))
        # the user must be able to edit the opportunity itself
        self.check_access('write')

    def _prepare_quote_values(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(self.env._('Set the Account on "%s" before creating a quote.', self.name))
        lines = [(0, 0, line._prepare_sale_line_values()) for line in self.line_ids]
        return {
            'partner_id': self.partner_id.id,
            'user_id': self.user_id.id,
            'team_id': self.team_id.id,
            'company_id': self.company_id.id,
            'origin': self.name,
            'modern_opportunity_id': self.id,
            'campaign_id': self.campaign_id.id,
            'medium_id': self.medium_id.id,
            'source_id': self.source_id.id,
            'order_line': lines,
        }

    def action_new_quote(self):
        """Create a quotation from the opportunity's products and make it the primary quote."""
        self.ensure_one()
        self._check_workflow_group(GROUP_QUOTE, self.env._('create quotes'))
        if self.is_closed:
            raise UserError(self.env._('Reopen the opportunity to create a new quote.'))
        quote = self.env['sale.order'].sudo().with_company(self.company_id).create(self._prepare_quote_values())
        self.sudo().primary_quote_id = quote
        self.message_post(body=self.env._('Quote %s created.', quote._get_html_link()))
        return self._action_open_sale_documents(quote)

    def _get_quote_to_confirm(self):
        self.ensure_one()
        quote = self.sudo().primary_quote_id
        if not quote or quote.state not in ('draft', 'sent'):
            quote = self.sudo().order_ids.filtered(lambda o: o.state in ('draft', 'sent'))[:1]
        return quote

    def action_confirm_sale(self):
        """Turn the primary quote into a sales order (Salesforce: Closed Won)."""
        self.ensure_one()
        self._check_workflow_group(GROUP_SALE_ORDER, self.env._('confirm sales orders'))
        quote = self._get_quote_to_confirm()
        if not quote:
            raise UserError(self.env._('There is no quote to confirm on "%s". Create a quote first.', self.name))
        self._confirm_quote(quote)
        return self._action_open_sale_documents(quote)

    def _confirm_quote(self, quote):
        quote = quote.sudo()
        quote.action_confirm()
        self.sudo().message_post(body=self.env._('Sales order %s confirmed.', quote._get_html_link()))
        return quote

    def action_create_invoice(self):
        """Draft the invoice for whatever the confirmed sales orders have ready to invoice."""
        self.ensure_one()
        self._check_workflow_group(GROUP_INVOICE, self.env._('create invoices'))
        invoices = self._create_invoices()
        return self._action_open_invoices(invoices)

    def _create_invoices(self):
        orders = self.sudo().order_ids.filtered(lambda o: o.state == 'sale' and o.invoice_status == 'to invoice')
        if not orders:
            raise UserError(self.env._(
                'Nothing is ready to invoice on "%s": confirm the sale first. Products invoiced on '
                'delivered quantities can be invoiced once they are delivered.', self.name))
        invoices = orders._create_invoices()
        for invoice in invoices:
            self.sudo().message_post(body=self.env._('Invoice %s drafted.', invoice._get_html_link()))
        return invoices

    def _action_open_sale_documents(self, orders):
        if not self.env['sale.order'].has_access('read'):
            return True
        action = self.env['ir.actions.act_window']._for_xml_id('sale.action_quotations_with_onboarding')
        action.update(context={'default_modern_opportunity_id': self.id, 'create': False})
        if len(orders) == 1:
            action.update(views=[(False, 'form')], view_mode='form', res_id=orders.id)
        else:
            action.update(domain=[('id', 'in', orders.ids)])
        return action

    def _action_open_invoices(self, invoices):
        if not self.env['account.move'].has_access('read'):
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': self.env._('Invoice drafted.'),
                           'next': {'type': 'ir.actions.act_window_close'}},
            }
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_out_invoice_type')
        action['context'] = {'create': False}
        if len(invoices) == 1:
            action.update(views=[(False, 'form')], view_mode='form', res_id=invoices.id)
        else:
            action['domain'] = [('id', 'in', invoices.ids)]
        return action

    def action_view_quotations(self):
        self.ensure_one()
        return self._action_open_sale_documents(self.sudo().order_ids.filtered(lambda o: o.state in ('draft', 'sent')))

    def action_view_sale_orders(self):
        self.ensure_one()
        return self._action_open_sale_documents(self.sudo().order_ids.filtered(lambda o: o.state == 'sale'))

    def action_view_invoices(self):
        self.ensure_one()
        return self._action_open_invoices(self.sudo().order_ids.filtered(lambda o: o.state == 'sale').invoice_ids)


class ModernCrmContactRole(models.Model):
    _name = 'modern.crm.contact.role'
    _description = 'CRM Opportunity Contact Role'
    _order = 'is_primary desc, sequence, id'

    opportunity_id = fields.Many2one(
        'modern.crm.opportunity', string='Opportunity', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    partner_id = fields.Many2one('res.partner', string='Contact', required=True)
    email = fields.Char(related='partner_id.email')
    phone = fields.Char(related='partner_id.phone')
    role_id = fields.Many2one('modern.crm.contact.role.type', string='Role')
    is_primary = fields.Boolean('Primary')

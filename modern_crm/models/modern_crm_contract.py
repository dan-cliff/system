import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

GROUP_SEND = 'modern_crm.group_modern_crm_contract_send'
GROUP_ACTIVATE = 'modern_crm.group_modern_crm_contract_activate'

# The contract's workflow: the signing portal and the automation on signing
# depend on these values, so they stay a fixed selection.
CONTRACT_STATES = [
    ('draft', 'Draft'),
    ('out_for_signature', 'Out for Signature'),
    ('declined', 'Declined'),
    ('signed', 'Signed'),
    ('activated', 'Activated'),
    ('expired', 'Expired'),
    ('cancelled', 'Cancelled'),
]


class ModernCrmContract(models.Model):
    _name = 'modern.crm.contract'
    _description = 'CRM Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_names_search = ['name', 'title', 'partner_id.name']
    # A contract made for an opportunity takes the opportunity's Organisation units.
    _org_parent_field = 'opportunity_id'

    def _default_template_id(self):
        return self.env.company.modern_crm_contract_template_id

    name = fields.Char('Contract Number', readonly=True, copy=False, default='/', index=True)
    title = fields.Char(
        'Contract Name', compute='_compute_from_opportunity', store=True, readonly=False,
        precompute=True, required=True, tracking=True)
    opportunity_id = fields.Many2one(
        'modern.crm.opportunity', string='Opportunity', index=True, tracking=True,
        domain="[('company_id', '=', company_id)]")
    partner_id = fields.Many2one(
        'res.partner', string='Account', required=True, tracking=True, index=True,
        compute='_compute_from_opportunity', store=True, readonly=False, precompute=True)
    quote_id = fields.Many2one(
        'sale.order', string='Quote', tracking=True, copy=False,
        compute='_compute_from_opportunity', store=True, readonly=False, precompute=True,
        domain="[('modern_opportunity_id', '=', opportunity_id)]",
        help='The quote this contract covers. With "Confirm the quote" switched on in Settings, it '
             'becomes a sales order once the contract is fully signed.')
    user_id = fields.Many2one(
        'res.users', string='Contract Owner', tracking=True, index=True,
        default=lambda self: self.env.user,
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]")
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)
    template_id = fields.Many2one(
        'modern.crm.contract.template', string='Template', default=_default_template_id,
        domain="[('company_id', 'in', (company_id, False))]")
    body = fields.Html('Contract Text', sanitize='email_outgoing', copy=True)
    start_date = fields.Date('Start Date', required=True, tracking=True,
                             default=fields.Date.context_today)
    term_months = fields.Integer('Contract Term (months)', default=12, tracking=True)
    end_date = fields.Date('End Date', compute='_compute_end_date', store=True)
    state = fields.Selection(
        CONTRACT_STATES, string='Status', default='draft', required=True, tracking=True,
        copy=False, index=True)
    signer_ids = fields.One2many(
        'modern.crm.contract.signer', 'contract_id', string='Signers', copy=True)
    sent_date = fields.Datetime('Sent for Signature On', readonly=True, copy=False)
    signed_date = fields.Datetime('Signed On', readonly=True, copy=False)
    activated_date = fields.Datetime('Activated On', readonly=True, copy=False)
    activated_by_id = fields.Many2one('res.users', string='Activated By', readonly=True, copy=False)
    signed_document_id = fields.Many2one(
        'ir.attachment', string='Signed Document', readonly=True, copy=False)
    special_terms = fields.Text('Special Terms')

    @api.depends('opportunity_id')
    def _compute_from_opportunity(self):
        for contract in self:
            opportunity = contract.opportunity_id
            if not opportunity:
                continue
            contract.partner_id = opportunity.partner_id or contract.partner_id
            contract.quote_id = opportunity.primary_quote_id or contract.quote_id
            if not contract.title:
                contract.title = opportunity.name

    @api.depends('start_date', 'term_months')
    def _compute_end_date(self):
        for contract in self:
            if contract.start_date and contract.term_months > 0:
                contract.end_date = contract.start_date + relativedelta(months=contract.term_months, days=-1)
            else:
                contract.end_date = False

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.template_id and self.template_id.term_months:
            self.term_months = self.template_id.term_months

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code(
                    'modern.crm.contract') or '/'
        contracts = super().create(vals_list)
        contracts.filtered(lambda c: c.template_id and not c.body)._render_body()
        return contracts

    def _compute_display_name(self):
        for contract in self:
            contract.display_name = (f'{contract.name} - {contract.title}' if contract.title
                                     else contract.name)

    # ------------------------------------------------------------------
    # Contract text
    # ------------------------------------------------------------------
    def _render_body(self):
        for contract in self:
            template = contract.template_id
            if not template.body:
                continue
            # Templates are set up by CRM administrators; render them with full
            # access so placeholders can read the quote and company details.
            rendered = self.env['mail.render.mixin'].sudo()._render_template(
                template.with_context(lang=contract.partner_id.lang or self.env.lang).body,
                contract._name, contract.ids, engine='qweb', options={'post_process': True})
            contract.body = rendered[contract.id]
            if template.term_months and not contract.term_months:
                contract.term_months = template.term_months

    def action_generate_text(self):
        self._check_draft()
        if any(not contract.template_id for contract in self):
            raise UserError(self.env._('Pick a contract template first.'))
        self._render_body()
        return True

    def _check_draft(self):
        if any(contract.state != 'draft' for contract in self):
            raise UserError(self.env._('Only draft contracts can be changed this way. Cancel the signature request first.'))

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------
    def _default_signer_values(self):
        self.ensure_one()
        customer = self.opportunity_id.contact_id or self.partner_id
        if customer.is_company and customer.child_ids:
            customer = customer.child_ids.filtered('email')[:1] or customer
        values = [{'contract_id': self.id, 'sequence': 10, 'partner_id': customer.id,
                   'role': self.env._('Customer')}]
        countersigner = self.template_id.countersigner_id
        if countersigner:
            values.append({'contract_id': self.id, 'sequence': 20, 'partner_id': countersigner.partner_id.id,
                           'role': self.env._('For %s', self.company_id.name)})
        return values

    def action_add_default_signers(self):
        for contract in self:
            contract._check_draft()
            if not contract.signer_ids:
                self.env['modern.crm.contract.signer'].create(contract._default_signer_values())
        return True

    def action_send_for_signature(self):
        if not self.env.user.has_group(GROUP_SEND):
            raise AccessError(self.env._('You are not allowed to send contracts for signature. '
                                         'Ask your CRM administrator for the permission.'))
        self.check_access('write')
        for contract in self:
            contract._check_draft()
            if not contract.body:
                raise UserError(self.env._('Add the contract text to %s before sending it.', contract.display_name))
            if not contract.signer_ids:
                contract.sudo().action_add_default_signers()
            missing = contract.signer_ids.filtered(lambda s: not s.partner_id.email)
            if missing:
                raise UserError(self.env._('These signers have no email address: %s',
                                           ', '.join(missing.partner_id.mapped('display_name'))))
        self = self.sudo()
        for contract in self:
            contract.signer_ids._reset_signature()
            contract.write({'state': 'out_for_signature', 'sent_date': fields.Datetime.now()})
            contract.message_subscribe(partner_ids=contract.signer_ids.partner_id.ids)
            contract._send_next_signature_requests()
        return True

    def _send_next_signature_requests(self):
        """Email the signers whose turn it is: everyone with the lowest sequence still to sign."""
        self.ensure_one()
        pending = self.signer_ids.filtered(lambda s: s.state in ('waiting', 'sent'))
        if not pending:
            return
        turn = min(pending.mapped('sequence'))
        pending.filtered(lambda s: s.sequence == turn and s.state == 'waiting')._send_request()

    def _on_signer_signed(self, signer):
        self.ensure_one()
        self.message_post(body=self.env._('Signed by %(name)s (%(signer)s).', name=signer.signed_by,
                                          signer=signer.partner_id.display_name))
        if all(s.state == 'signed' for s in self.signer_ids):
            self._on_fully_signed()
        else:
            self._send_next_signature_requests()

    def _on_signer_declined(self, signer):
        self.ensure_one()
        self.state = 'declined'
        self.signer_ids.filtered(lambda s: s.state in ('waiting', 'sent')).state = 'cancelled'
        self.message_post(
            body=self.env._('%(signer)s declined to sign: %(reason)s', signer=signer.partner_id.display_name,
                            reason=signer.decline_reason or self.env._('no reason given')),
            partner_ids=self.user_id.partner_id.ids)
        if self.user_id:
            self.activity_schedule('mail.mail_activity_data_todo', user_id=self.user_id.id,
                                   summary=self.env._('Contract declined by %s', signer.partner_id.display_name),
                                   note=signer.decline_reason)

    def _render_signed_pdf(self):
        self.ensure_one()
        pdf, _ftype = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'modern_crm.action_report_modern_crm_contract', self.ids)
        return pdf

    def _on_fully_signed(self):
        """Store the signed PDF, send it to the signers, then do what Settings ask for."""
        self.ensure_one()
        self.write({'state': 'signed', 'signed_date': fields.Datetime.now()})
        # flush so the PDF shows the signatures just written
        self.env.flush_all()
        attachment = self.env['ir.attachment']
        try:
            with self.env.cr.savepoint():
                pdf = self._render_signed_pdf()
        except Exception as error:  # noqa: BLE001 - never lose the signatures over the PDF
            _logger.exception('Contract %s: could not create the signed PDF', self.name)
            self.message_post(body=self.env._('Could not create the signed PDF: %s', error),
                              partner_ids=self.user_id.partner_id.ids)
        else:
            attachment = attachment.sudo().create({
                'name': self.env._('%s (signed).pdf', self.name),
                'raw': pdf,
                'mimetype': 'application/pdf',
                'res_model': self._name,
                'res_id': self.id,
            })
            self.signed_document_id = attachment
        template = self.env.ref('modern_crm.mail_template_contract_signed', raise_if_not_found=False)
        if template:
            self.message_post_with_source(
                template, subtype_xmlid='mail.mt_comment', attachment_ids=attachment.ids)
        else:
            self.message_post(body=self.env._('Contract fully signed.'), attachment_ids=attachment.ids)
        self._run_signed_automation()

    def _run_signed_automation(self):
        company = self.company_id
        if company.modern_crm_activate_on_signature:
            self._activate()
        opportunity = self.opportunity_id.sudo()
        quote = self.quote_id.sudo()
        if not (company.modern_crm_confirm_on_signature and quote and quote.state in ('draft', 'sent')):
            return
        try:
            with self.env.cr.savepoint():
                if opportunity:
                    opportunity._confirm_quote(quote)
                else:
                    quote.action_confirm()
                self.message_post(body=self.env._('Sales order %s confirmed.', quote._get_html_link()))
                if company.modern_crm_invoice_on_signature and quote.invoice_status == 'to invoice':
                    invoices = quote._create_invoices()
                    self.message_post(body=self.env._(
                        'Invoice drafted: %s', ', '.join(inv._get_html_link() for inv in invoices)))
        except UserError as error:
            # The contract stays signed; tell the owner what still needs doing.
            _logger.info('Contract %s: could not confirm quote %s: %s', self.name, quote.name, error)
            self.message_post(body=self.env._('Could not confirm the quote automatically: %s', error),
                              partner_ids=self.user_id.partner_id.ids)

    def action_cancel_signature(self):
        self.check_access('write')
        for contract in self:
            if contract.state not in ('out_for_signature', 'declined'):
                raise UserError(self.env._('%s is not out for signature.', contract.display_name))
        self.sudo().signer_ids._reset_signature(state='draft')
        self.write({'state': 'draft', 'sent_date': False})
        self.message_post(body=self.env._('Signature request cancelled.'))
        return True

    # ------------------------------------------------------------------
    # Activation and lifecycle
    # ------------------------------------------------------------------
    def action_activate(self):
        if not self.env.user.has_group(GROUP_ACTIVATE):
            raise AccessError(self.env._('You are not allowed to activate contracts. '
                                         'Ask your CRM administrator for the permission.'))
        self.check_access('write')
        for contract in self:
            if contract.state not in ('draft', 'signed'):
                raise UserError(self.env._('Only draft or signed contracts can be activated.'))
        self.sudo()._activate()
        return True

    def _activate(self):
        # activated by the last signature (a portal or public user): no one to name
        user = self.env.user if not self.env.user.share else self.env['res.users']
        self.write({'state': 'activated', 'activated_date': fields.Datetime.now(),
                    'activated_by_id': user.id})

    def action_cancel(self):
        if any(contract.state in ('activated', 'expired') for contract in self):
            raise UserError(self.env._('Activated contracts run until they expire and cannot be cancelled.'))
        self.sudo().signer_ids.filtered(lambda s: s.state in ('waiting', 'sent'))._reset_signature(state='cancelled')
        self.write({'state': 'cancelled'})
        return True

    def action_set_draft(self):
        if any(contract.state not in ('cancelled', 'declined') for contract in self):
            raise UserError(self.env._('Only cancelled or declined contracts can be reset to draft.'))
        self.sudo().signer_ids._reset_signature(state='draft')
        self.write({'state': 'draft'})
        return True

    def action_print(self):
        return self.env.ref('modern_crm.action_report_modern_crm_contract').report_action(self)

    def action_view_signed_document(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': f'/web/content/{self.signed_document_id.id}?download=true'}

    @api.model
    def _cron_expire_contracts(self):
        today = fields.Date.context_today(self)
        expired = self.search([('state', '=', 'activated'), ('end_date', '!=', False), ('end_date', '<', today)])
        expired.write({'state': 'expired'})

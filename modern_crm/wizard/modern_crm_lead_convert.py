from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class ModernCrmLeadConvert(models.TransientModel):
    """Salesforce's Convert Lead: an Account, a Contact and (optionally) an Opportunity."""
    _name = 'modern.crm.lead.convert'
    _description = 'Convert CRM Lead'

    lead_id = fields.Many2one('modern.crm.lead', string='Lead', required=True, ondelete='cascade')
    account_action = fields.Selection(
        [('create', 'Create a new account'), ('existing', 'Choose an existing account'),
         ('none', 'No account (private person)')],
        string='Account', required=True, compute='_compute_from_lead', store=True, precompute=True,
        readonly=False)
    account_name = fields.Char('Account Name', compute='_compute_from_lead', store=True, precompute=True, readonly=False)
    account_id = fields.Many2one(
        'res.partner', string='Existing Account', compute='_compute_from_lead', store=True, precompute=True, readonly=False,
        domain="[('is_company', '=', True)]")
    contact_action = fields.Selection(
        [('create', 'Create a new contact'), ('existing', 'Choose an existing contact')],
        string='Contact', required=True, compute='_compute_from_lead', store=True, precompute=True, readonly=False)
    contact_id = fields.Many2one(
        'res.partner', string='Existing Contact', compute='_compute_from_lead', store=True, precompute=True, readonly=False,
        domain="[('is_company', '=', False)]")
    create_opportunity = fields.Boolean('Create an Opportunity', default=True)
    opportunity_name = fields.Char('Opportunity Name', compute='_compute_from_lead', store=True, precompute=True, readonly=False)
    close_date = fields.Date('Close Date', default=lambda self: fields.Date.context_today(self) + timedelta(days=30))
    amount = fields.Monetary('Amount', currency_field='currency_id')
    currency_id = fields.Many2one(related='lead_id.company_id.currency_id')
    user_id = fields.Many2one('res.users', string='Owner', compute='_compute_from_lead', store=True, precompute=True,
                              readonly=False, domain="[('share', '=', False)]")

    @api.depends('lead_id')
    def _compute_from_lead(self):
        Partner = self.env['res.partner']
        for wizard in self:
            lead = wizard.lead_id
            wizard.account_name = lead.company_name
            wizard.account_id = (lead.partner_id.commercial_partner_id if lead.partner_id.parent_id
                                 else Partner.search([('is_company', '=', True), ('name', '=ilike', lead.company_name)],
                                                     limit=1) if lead.company_name else False)
            wizard.account_action = ('existing' if wizard.account_id
                                     else 'create' if lead.company_name else 'none')
            wizard.contact_id = lead.partner_id if lead.partner_id and not lead.partner_id.is_company else False
            wizard.contact_action = 'existing' if wizard.contact_id else 'create'
            wizard.opportunity_name = lead.company_name and f'{lead.company_name} - {lead.name}' or lead.name
            wizard.user_id = lead.user_id or self.env.user

    @api.onchange('account_id')
    def _onchange_account_id(self):
        if self.account_id:
            self.account_action = 'existing'

    def _lead_address_values(self):
        lead = self.lead_id
        return {
            'street': lead.street, 'street2': lead.street2, 'city': lead.city, 'zip': lead.zip,
            'state_id': lead.state_id.id, 'country_id': lead.country_id.id,
        }

    def _get_account(self):
        lead = self.lead_id
        if self.account_action == 'existing':
            if not self.account_id:
                raise UserError(self.env._('Choose the existing account.'))
            return self.account_id
        if self.account_action == 'none':
            return self.env['res.partner']
        if not self.account_name:
            raise UserError(self.env._('Enter the name of the new account.'))
        return self.env['res.partner'].create(dict(
            self._lead_address_values(), name=self.account_name, is_company=True, website=lead.website,
            phone=lead.phone, company_id=False, user_id=self.user_id.id))

    def _get_contact(self, account):
        lead = self.lead_id
        if self.contact_action == 'existing':
            if not self.contact_id:
                raise UserError(self.env._('Choose the existing contact.'))
            if account and not self.contact_id.parent_id:
                self.contact_id.parent_id = account
            return self.contact_id
        values = dict(name=lead.name, email=lead.email, phone=lead.phone or lead.mobile,
                      function=lead.job_title, is_company=False, user_id=self.user_id.id)
        if account:
            values['parent_id'] = account.id
            values['type'] = 'contact'
        else:
            values.update(self._lead_address_values())
        return self.env['res.partner'].create(values)

    def action_convert(self):
        self.ensure_one()
        lead = self.lead_id
        lead._check_open()
        account = self._get_account()
        contact = self._get_contact(account)
        opportunity = self.env['modern.crm.opportunity']
        if self.create_opportunity:
            opportunity = opportunity.create({
                'name': self.opportunity_name or lead.name,
                'partner_id': (account or contact).id,
                'contact_id': contact.id,
                'user_id': self.user_id.id,
                'team_id': lead.team_id.id,
                'company_id': lead.company_id.id,
                'close_date': self.close_date,
                'amount': self.amount,
                'lead_source_id': lead.lead_source_id.id,
                'lead_id': lead.id,
                'description': lead.description,
                'campaign_id': lead.campaign_id.id,
                'medium_id': lead.medium_id.id,
                'source_id': lead.source_id.id,
                'contact_role_ids': [(0, 0, {'partner_id': contact.id, 'is_primary': True})],
            })
        lead.write({
            'state': 'converted',
            'converted_date': fields.Datetime.now(),
            'converted_account_id': account.id,
            'converted_contact_id': contact.id,
            'converted_opportunity_id': opportunity.id,
            'partner_id': contact.id,
        })
        lead.message_post(body=self.env._('Lead converted.'))
        if opportunity:
            return {'type': 'ir.actions.act_window', 'res_model': 'modern.crm.opportunity',
                    'view_mode': 'form', 'res_id': opportunity.id}
        return {'type': 'ir.actions.act_window', 'res_model': 'res.partner', 'view_mode': 'form',
                'res_id': (account or contact).id}

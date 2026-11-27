from odoo import api, fields, models


class AdvancedAccount(models.Model):
    """A company or organisation you do business with (as in Salesforce or
    HubSpot). Its details live on a company partner, which every other app
    keeps using; Contacts are linked to it and sit under that partner."""
    _name = 'advanced.account'
    _description = 'Account'
    _inherit = ['advanced.partner.delegation', 'mail.thread', 'mail.activity.mixin']
    _inherits = {'res.partner': 'partner_id'}
    _order = 'name, id'
    _rec_names_search = ['name', 'email', 'ref', 'vat']

    partner_id = fields.Many2one(
        'res.partner', string='Partner', required=True, ondelete='cascade', index=True,
        bypass_search_access=True)
    account_type_id = fields.Many2one('advanced.account.type', string='Account Type', tracking=True)
    contact_ids = fields.One2many('advanced.contact', 'account_id', string='Contacts')
    contact_count = fields.Integer('Contact Count', compute='_compute_contact_count')

    _partner_uniq = models.Constraint('UNIQUE (partner_id)', 'This partner already has an Account.')

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'company_id' in fields_list and not defaults.get('company_id'):
            defaults['company_id'] = self.env.company.id
        if 'user_id' in fields_list and 'user_id' not in defaults:
            defaults['user_id'] = self.env.uid
        return defaults

    @api.depends('contact_ids')
    def _compute_contact_count(self):
        counts = dict(self.env['advanced.contact']._read_group(
            [('account_id', 'in', self.ids)], ['account_id'], ['__count']))
        for account in self:
            account.contact_count = counts.get(account, 0)

    def _prepare_partner_vals(self, own, partner_vals):
        if not own.get('partner_id') and not self:
            partner_vals.setdefault('is_company', True)
        return partner_vals

    @api.model_create_multi
    def create(self, vals_list):
        accounts = super().create(vals_list)
        # Contacts already sitting under these partners join the new Accounts.
        contacts = self.env['advanced.contact'].sudo().search([
            ('account_id', '=', False), ('partner_id.parent_id', 'in', accounts.partner_id.ids)])
        for contact in contacts:
            contact.account_id = accounts.filtered(lambda a: a.partner_id == contact.partner_id.parent_id)[:1]
        return accounts

    @api.model
    def _for_partners(self, partners):
        """{partner id: Account} for the Account each partner belongs to (the
        Account of its company, so a Contact or an invoice address maps too)."""
        commercial = partners.commercial_partner_id
        accounts = self.sudo().with_context(active_test=False).search([('partner_id', 'in', commercial.ids)])
        by_partner = {account.partner_id.id: account.sudo(False) for account in accounts}
        return {partner.id: by_partner.get(partner.commercial_partner_id.id, self.browse())
                for partner in partners}

    def action_view_contacts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_accounts.advanced_contact_action')
        action.update(domain=[('account_id', '=', self.id)],
                      context={'default_account_id': self.id})
        return action

    def action_open_partner(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'res.partner', 'res_id': self.partner_id.id,
                'view_mode': 'form'}

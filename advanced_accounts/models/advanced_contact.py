from odoo import api, fields, models
from odoo.exceptions import UserError


class AdvancedContact(models.Model):
    """A person, usually at an Account (as in Salesforce or HubSpot). Its
    details live on a person partner placed under the Account's partner. When
    the Contact needs to log in, its user is built on that same partner, so the
    Contact and the user always share one name, email and phone."""
    _name = 'advanced.contact'
    _description = 'Contact'
    _inherit = ['advanced.partner.delegation', 'mail.thread', 'mail.activity.mixin']
    _inherits = {'res.partner': 'partner_id'}
    _order = 'name, id'
    _rec_names_search = ['name', 'email', 'account_id.name']

    partner_id = fields.Many2one(
        'res.partner', string='Partner', required=True, ondelete='cascade', index=True,
        bypass_search_access=True)
    account_id = fields.Many2one(
        'advanced.account', string='Account', index='btree_not_null', tracking=True, ondelete='set null',
        compute='_compute_account_id', store=True, readonly=False, precompute=True)
    login_user_id = fields.Many2one(
        'res.users', string='User', compute='_compute_login_user_id', compute_sudo=True,
        help='The user this Contact logs in with. It shares the Contact\'s name, email and phone.')

    _partner_uniq = models.Constraint('UNIQUE (partner_id)', 'This partner already has a Contact.')

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'company_id' in fields_list and not defaults.get('company_id'):
            defaults['company_id'] = self.env.company.id
        if 'user_id' in fields_list and 'user_id' not in defaults:
            defaults['user_id'] = self.env.uid
        return defaults

    @api.depends('partner_id.parent_id')
    def _compute_account_id(self):
        accounts = self.env['advanced.account']._for_partners(self.partner_id.parent_id)
        for contact in self:
            parent = contact.partner_id.parent_id
            contact.account_id = accounts.get(parent.id) if parent else False

    @api.depends('name', 'account_id.name')
    @api.depends_context('formatted_display_name')
    def _compute_display_name(self):
        # The Contact pickers list "Contact Name (Account Name)" to tell people
        # with the same name apart; the chosen Contact then shows its name only.
        formatted = self.env.context.get('formatted_display_name')
        for contact in self:
            name = contact.name or ''
            if formatted and contact.account_id:
                name = f'{name} --({contact.account_id.name})--'
            contact.display_name = name

    @api.depends('partner_id.user_ids')
    def _compute_login_user_id(self):
        for contact in self:
            contact.login_user_id = contact.partner_id.with_context(active_test=False).user_ids[:1]

    def _prepare_partner_vals(self, own, partner_vals):
        if not self and not own.get('partner_id'):
            partner_vals.setdefault('is_company', False)
            partner_vals.setdefault('type', 'contact')
        if 'account_id' in own:
            parent = self.env['advanced.account'].sudo().browse(own['account_id']).partner_id
            current = self.partner_id or self.env['res.partner'].browse(own.get('partner_id'))
            if not current or current.parent_id != parent:
                partner_vals['parent_id'] = parent.id
        return partner_vals

    @api.model
    def _for_partners(self, partners):
        """{partner id: Contact} for the partners that are Contacts."""
        contacts = self.sudo().with_context(active_test=False).search([('partner_id', 'in', partners.ids)])
        return {contact.partner_id.id: contact.sudo(False) for contact in contacts}

    @api.model
    def _adopt_partners(self, partners):
        """Give partners made outside Advanced Accounts (by the website, the
        Point of Sale, lead conversion, an import, ...) their Account or
        Contact, so they can be picked like any other. Skips our own users,
        employees and companies: those aren't customers."""
        partners = partners.sudo().exists().filtered('active')
        if not partners:
            return
        env = self.env(su=True)
        candidates = partners | partners.commercial_partner_id
        excluded = env['res.users'].with_context(active_test=False).search(
            [('partner_id', 'in', candidates.ids), ('share', '=', False)]).partner_id
        excluded |= env['res.company'].with_context(active_test=False).search([]).partner_id
        if 'hr.employee' in env and 'work_contact_id' in env['hr.employee']._fields:
            excluded |= env['hr.employee'].with_context(active_test=False).search(
                [('work_contact_id', 'in', candidates.ids)]).work_contact_id
        Account, Contact = env['advanced.account'], env['advanced.contact']

        companies = candidates.filtered(lambda p: p.is_company and p.active) - excluded
        have_account = Account.with_context(active_test=False).search(
            [('partner_id', 'in', companies.ids)]).partner_id
        if companies - have_account:
            Account.create([{'partner_id': p.id} for p in companies - have_account])

        people = partners.filtered(
            lambda p: not p.is_company and (p.type == 'contact' or not p.parent_id)) - excluded
        have_contact = Contact.with_context(active_test=False).search([('partner_id', 'in', people.ids)]).partner_id
        if people - have_contact:
            Contact.create([{'partner_id': p.id} for p in people - have_contact])

    def action_create_user(self):
        """Open a new portal user built on this Contact (same partner), so the
        two stay in sync."""
        self.ensure_one()
        if self.login_user_id:
            return self.action_open_user()
        if not self.env.user.has_group('advanced_accounts.group_advanced_contact_create_user'):
            raise UserError(self.env._('You are not allowed to create users for Contacts.'))
        self.check_access('write')
        if not self.email:
            raise UserError(self.env._('Add an email address to %s first: it is their login.', self.name))
        user = self.env['res.users'].sudo().create({
            'partner_id': self.partner_id.id,
            'login': self.email,
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        self.message_post(body=self.env._('Portal user %s created.', user.login))
        return self.action_open_user()

    def action_open_user(self):
        self.ensure_one()
        user = self.partner_id.with_context(active_test=False).user_ids[:1]
        return {'type': 'ir.actions.act_window', 'res_model': 'res.users', 'res_id': user.id,
                'view_mode': 'form', 'name': self.env._('User')}

from odoo import api, fields, models, tools
from odoo.exceptions import UserError

# The lead's workflow: code depends on these values (conversion, disqualifying),
# so they stay a fixed selection. Why a lead was disqualified is an option list.
LEAD_STATES = [
    ('new', 'New'),
    ('working', 'Working'),
    ('nurturing', 'Nurturing'),
    ('converted', 'Converted'),
    ('disqualified', 'Disqualified'),
]


class ModernCrmLead(models.Model):
    _name = 'modern.crm.lead'
    _description = 'CRM Lead'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'utm.mixin']
    _order = 'id desc'
    _primary_email = 'email'
    _rec_names_search = ['name', 'company_name', 'email']

    def _default_source(self):
        return self.env.ref('modern_crm.lead_source_other', raise_if_not_found=False)

    name = fields.Char(
        'Name', compute='_compute_name', store=True, readonly=False, index='trigram', tracking=True)
    first_name = fields.Char('First Name')
    last_name = fields.Char('Last Name')
    job_title = fields.Char('Title')
    company_name = fields.Char('Company Name', tracking=True)
    email = fields.Char(tracking=True)
    phone = fields.Char()
    mobile = fields.Char()
    website = fields.Char()
    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char()
    zip = fields.Char()
    state_id = fields.Many2one(
        'res.country.state', string='State', domain="[('country_id', '=?', country_id)]")
    country_id = fields.Many2one('res.country', string='Country')
    industry_id = fields.Many2one('modern.crm.industry', string='Industry', tracking=True)
    lead_source_id = fields.Many2one(
        'modern.crm.lead.source', string='Lead Source', tracking=True, default=_default_source)
    rating_id = fields.Many2one('modern.crm.lead.rating', string='Rating', tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    annual_revenue = fields.Monetary('Annual Revenue', currency_field='currency_id')
    employee_count = fields.Integer('No. of Employees')
    description = fields.Html()
    user_id = fields.Many2one(
        'res.users', string='Lead Owner', tracking=True, index=True,
        default=lambda self: self.env.user,
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]")
    team_id = fields.Many2one('crm.team', string='Sales Team', tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string='Existing Contact',
        help='A contact already in the system for this lead, used when converting it.')
    state = fields.Selection(
        LEAD_STATES, string='Status', default='new', required=True, tracking=True, index=True,
        copy=False)
    disqualify_reason_id = fields.Many2one(
        'modern.crm.disqualify.reason', string='Disqualify Reason', tracking=True, copy=False)
    disqualify_note = fields.Text('Disqualify Notes', copy=False)
    converted_date = fields.Datetime('Converted On', readonly=True, copy=False)
    converted_account_id = fields.Many2one(
        'res.partner', string='Converted Account', readonly=True, copy=False)
    converted_contact_id = fields.Many2one(
        'res.partner', string='Converted Contact', readonly=True, copy=False)
    converted_opportunity_id = fields.Many2one(
        'modern.crm.opportunity', string='Converted Opportunity', readonly=True, copy=False)
    color = fields.Integer('Color Index')

    @api.depends('first_name', 'last_name')
    def _compute_name(self):
        for lead in self:
            full_name = ' '.join(p for p in (lead.first_name, lead.last_name) if p)
            if full_name:
                lead.name = full_name
            elif not lead.name:
                lead.name = lead.company_name or self.env._('New Lead')

    @api.onchange('email')
    def _onchange_email(self):
        if self.email and not self.partner_id:
            email = tools.email_normalize(self.email)
            if email:
                self.partner_id = self.env['res.partner'].search(
                    [('email_normalized', '=', email)], limit=1)

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        partner = self.partner_id
        if not partner:
            return
        for field in ('email', 'phone', 'street', 'street2', 'city', 'zip', 'state_id', 'country_id'):
            if not self[field] and partner[field]:
                self[field] = partner[field]
        if not self.company_name and partner.parent_id:
            self.company_name = partner.parent_id.name

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _check_open(self):
        if any(lead.state in ('converted', 'disqualified') for lead in self):
            raise UserError(self.env._('Reopen the lead first: it is already converted or disqualified.'))

    def action_set_working(self):
        self._check_open()
        self.write({'state': 'working'})

    def action_set_nurturing(self):
        self._check_open()
        self.write({'state': 'nurturing'})

    def action_reopen(self):
        if any(lead.state == 'converted' for lead in self):
            raise UserError(self.env._('A converted lead cannot be reopened.'))
        self.write({'state': 'working', 'disqualify_reason_id': False, 'disqualify_note': False})

    def action_disqualify(self):
        self._check_open()
        return {
            'name': self.env._('Disqualify Lead'),
            'type': 'ir.actions.act_window',
            'res_model': 'modern.crm.reason.wizard',
            'view_mode': 'form',
            'views': [(self.env.ref('modern_crm.modern_crm_reason_wizard_view_form_disqualify').id, 'form')],
            'target': 'new',
            'context': {'default_lead_ids': self.ids, 'default_mode': 'disqualify'},
        }

    def action_convert(self):
        self.ensure_one()
        self._check_open()
        return {
            'name': self.env._('Convert Lead'),
            'type': 'ir.actions.act_window',
            'res_model': 'modern.crm.lead.convert',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_lead_id': self.id},
        }

    def action_view_opportunity(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'modern.crm.opportunity',
            'view_mode': 'form',
            'res_id': self.converted_opportunity_id.id,
        }

    # ------------------------------------------------------------------
    # Email to lead: a mail alias pointing at this model opens a lead per email
    # ------------------------------------------------------------------
    @api.model
    def message_new(self, msg_dict, custom_values=None):
        name, email = tools.parse_contact_from_email(msg_dict.get('from') or '')
        first, _sep, last = (name or '').strip().rpartition(' ')
        values = {
            'first_name': first or False,
            'last_name': last or email,
            'email': email,
            'description': msg_dict.get('body'),
            'lead_source_id': (self.env.ref('modern_crm.lead_source_email', raise_if_not_found=False)
                               or self.env['modern.crm.lead.source']).id,
            'user_id': False,
        }
        partner = self.env['res.partner'].search([('email_normalized', '=', tools.email_normalize(email))],
                                                 limit=1) if email else False
        if partner:
            values['partner_id'] = partner.id
            values['company_name'] = partner.parent_id.name or False
        values.update(custom_values or {})
        return super().message_new(msg_dict, custom_values=values)

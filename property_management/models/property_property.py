# -*- coding: utf-8 -*-
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# How the business holds the property. Kept as a fixed selection (not an
# option model) because the form, the lease defaults and the totals depend
# on these exact values (CLAUDE.md > Choice fields, exceptions).
OWNERSHIP = [
    ('leased_in', 'Leased (Externally Owned)'),
    ('owned_occupied', 'Owned and Occupied'),
    ('owned_leased_out', 'Owned and Leased Out'),
    ('owned_mixed', 'Owned, Part Occupied and Part Leased Out'),
]
OWNED = ('owned_occupied', 'owned_leased_out', 'owned_mixed')
LEASES_OUT = ('owned_leased_out', 'owned_mixed')


class PropertyProperty(models.Model):
    _name = 'property.property'
    _description = 'Property'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'image.mixin']
    _order = 'name, id'
    _rec_names_search = ['name', 'reference', 'street', 'city']

    name = fields.Char(required=True, tracking=True)
    reference = fields.Char(
        readonly=True, copy=False, default=lambda self: self.env._('New'), index='trigram',
        help='Numbered automatically when the property is saved.',
    )
    active = fields.Boolean(default=True)
    color = fields.Integer()
    user_id = fields.Many2one(
        'res.users', string='Property Manager', default=lambda self: self.env.user, tracking=True,
        index=True, domain=[('share', '=', False)],
        help='The person in the business who looks after this property.',
    )
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, tracking=True, index=True,
    )
    currency_id = fields.Many2one(related='company_id.currency_id')

    category_id = fields.Many2one(
        'property.category', string='Category', tracking=True, ondelete='restrict',
        help='Residential, commercial, …',
    )
    type_id = fields.Many2one(
        'property.type', string='Property Type', tracking=True, ondelete='restrict',
        domain="['|', ('category_ids', '=', False), ('category_ids', 'in', category_id)]",
    )
    stage_id = fields.Many2one(
        'property.stage', string='Status', tracking=True, ondelete='restrict', index=True,
        default=lambda self: self.env['property.stage'].search([], limit=1),
        group_expand='_read_group_stage_ids',
    )
    ownership = fields.Selection(
        OWNERSHIP, required=True, default='leased_in', tracking=True,
        help='Leased: we lease the premises from an external owner.\n'
             'Owned and Occupied: we own the premises and use them ourselves.\n'
             'Owned and Leased Out: we own the premises and lease them to others.\n'
             'Owned, Part Occupied and Part Leased Out: we use part and lease out the rest.',
    )
    is_owned = fields.Boolean(compute='_compute_ownership_flags')
    leases_out = fields.Boolean(compute='_compute_ownership_flags')

    # Address
    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one(
        'res.country.state', string='State', ondelete='restrict',
        domain="[('country_id', '=?', country_id)]",
    )
    zip = fields.Char()
    country_id = fields.Many2one(
        'res.country', string='Country', ondelete='restrict',
        default=lambda self: self.env.company.country_id,
    )
    address = fields.Char(compute='_compute_address', string='Address')

    # Details
    description = fields.Html()
    floor_area = fields.Float(string='Floor Area (m²)', digits=(16, 2))
    land_area = fields.Float(string='Land Area (m²)', digits=(16, 2))
    storeys = fields.Integer()
    bedrooms = fields.Integer()
    bathrooms = fields.Integer()
    car_spaces = fields.Integer(string='Car Spaces')
    year_built = fields.Date(
        string='Year Built', help='Stored as 1 January of the year; the picker only offers years.',
    )
    title_reference = fields.Char(string='Title Reference', help='Certificate of title, folio or lot and plan.')
    local_authority = fields.Char(string='Local Authority', help='The council or local government area.')
    zoning = fields.Char()

    # Ownership (owned properties)
    acquisition_date = fields.Date(string='Acquired On', tracking=True)
    purchase_price = fields.Monetary(tracking=True)
    current_value = fields.Monetary(string='Current Value', tracking=True)
    valuation_date = fields.Date(string='Valued On')
    valuer = fields.Char(string='Valued By')
    disposal_date = fields.Date(string='Disposed On', tracking=True)
    sale_price = fields.Monetary(string='Sale Price')

    # External parties
    landlord_id = fields.Many2one(
        'res.partner', string='Landlord', tracking=True, ondelete='restrict',
        help='The external owner of a property we lease.',
    )
    agent_id = fields.Many2one(
        'res.partner', string='Managing Agent', tracking=True, ondelete='restrict',
        help='The agent who manages the property on behalf of its owner.',
    )

    # Related records
    lease_ids = fields.One2many('property.lease', 'property_id', string='Leases')
    contract_ids = fields.One2many('property.contract', 'property_id', string='Contracts')
    photo_ids = fields.One2many('property.photo', 'property_id', string='Photos')
    floor_plan_ids = fields.One2many('property.floor.plan', 'property_id', string='Floor Plans')
    lease_count = fields.Integer(compute='_compute_counts')
    contract_count = fields.Integer(compute='_compute_counts')
    photo_count = fields.Integer(compute='_compute_counts')
    floor_plan_count = fields.Integer(compute='_compute_counts')

    # Lease summary
    active_lease_ids = fields.Many2many(
        'property.lease', compute='_compute_lease_summary', string='Current Leases')
    tenant_ids = fields.Many2many(
        'res.partner', compute='_compute_lease_summary', string='Tenants',
        help='The tenants of the leases currently in force on this property.')
    next_lease_end = fields.Date(
        compute='_compute_lease_summary', string='Next Lease Expiry',
        help='The earliest end date of the leases currently in force.')
    annual_rent_payable = fields.Monetary(
        compute='_compute_lease_summary', string='Annual Rent Paid',
        help='Yearly rent of the leases in force where the business is the tenant.')
    annual_rent_receivable = fields.Monetary(
        compute='_compute_lease_summary', string='Annual Rent Received',
        help='Yearly rent of the leases in force where the business is the landlord.')
    annual_contract_cost = fields.Monetary(
        compute='_compute_lease_summary', string='Annual Contract Costs',
        help='Yearly cost of the active contracts for this property.')

    notes = fields.Html()

    _reference_company_unique = models.Constraint(
        'UNIQUE(reference, company_id)', 'A property reference must be unique per company.')

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([], order=stages._order)

    @api.depends('ownership')
    def _compute_ownership_flags(self):
        for prop in self:
            prop.is_owned = prop.ownership in OWNED
            prop.leases_out = prop.ownership in LEASES_OUT

    @api.depends('street', 'street2', 'city', 'state_id', 'zip', 'country_id')
    def _compute_address(self):
        for prop in self:
            parts = [prop.street, prop.street2, prop.city,
                     ' '.join(p for p in (prop.state_id.code, prop.zip) if p), prop.country_id.name]
            prop.address = ', '.join(p for p in parts if p)

    def _compute_counts(self):
        for field, model in (('lease_count', 'property.lease'), ('contract_count', 'property.contract'),
                             ('photo_count', 'property.photo'), ('floor_plan_count', 'property.floor.plan')):
            counts = dict(self.env[model]._read_group(
                [('property_id', 'in', self.ids)], ['property_id'], ['__count']))
            for prop in self:
                prop[field] = counts.get(prop, 0)

    @api.depends('lease_ids.state', 'lease_ids.date_end', 'lease_ids.annual_rent', 'lease_ids.partner_id',
                 'contract_ids.state', 'contract_ids.annual_amount')
    def _compute_lease_summary(self):
        for prop in self:
            leases = prop.lease_ids.filtered(lambda lease: lease.state == 'active')
            prop.active_lease_ids = leases
            prop.tenant_ids = leases.filtered(lambda lease: lease.lease_type == 'out').partner_id
            ends = [d for d in leases.mapped('date_end') if d]
            prop.next_lease_end = min(ends) if ends else False
            prop.annual_rent_payable = sum(leases.filtered(lambda lease: lease.lease_type == 'in')
                                           .mapped('annual_rent_company'))
            prop.annual_rent_receivable = sum(leases.filtered(lambda lease: lease.lease_type == 'out')
                                              .mapped('annual_rent_company'))
            prop.annual_contract_cost = sum(prop.contract_ids.filtered(lambda c: c.state == 'active')
                                            .mapped('annual_amount_company'))

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.type_id.category_ids and self.category_id not in self.type_id.category_ids:
            self.type_id = False

    @api.onchange('ownership')
    def _onchange_ownership(self):
        if self.ownership in OWNED:
            self.landlord_id = False

    # ── Year Built is stored as 1 January (CLAUDE.md > Dates) ────────────

    @api.model
    def _year_start(self, value):
        if not value:
            return value
        if isinstance(value, int):
            return date(value, 1, 1)
        return fields.Date.to_date(value).replace(month=1, day=1)

    @api.constrains('year_built')
    def _check_year_built(self):
        for prop in self:
            if prop.year_built and not 1000 <= prop.year_built.year <= 2999:
                raise ValidationError(self.env._('Year Built must be a four-digit year, such as 1985.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('year_built'):
                vals['year_built'] = self._year_start(vals['year_built'])
            if not vals.get('reference') or vals['reference'] == self.env._('New'):
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['reference'] = self.env['ir.sequence'].with_company(company).next_by_code(
                    'property.property') or self.env._('New')
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('year_built'):
            vals = dict(vals, year_built=self._year_start(vals['year_built']))
        return super().write(vals)

    @api.depends('reference')
    def _compute_display_name(self):
        for prop in self:
            prop.display_name = prop.name if not prop.reference or prop.reference == self.env._('New') \
                else '[%s] %s' % (prop.reference, prop.name)

    # ── Smart buttons ────────────────────────────────────────────────────

    def _related_action(self, xmlid, extra_context=None):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(xmlid)
        context = {'default_property_id': self.id, 'search_default_property_id': self.id}
        context.update(extra_context or {})
        action.update({'domain': [('property_id', '=', self.id)], 'context': context})
        return action

    def action_view_leases(self):
        return self._related_action('property_management.action_property_lease')

    def action_view_contracts(self):
        return self._related_action('property_management.action_property_contract')

    def action_upload_photos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Upload Photos'),
            'res_model': 'property.photo.upload',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_property_id': self.id},
        }

    def action_new_lease(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('New Lease'),
            'res_model': 'property.lease',
            'view_mode': 'form',
            'context': {'default_property_id': self.id},
        }

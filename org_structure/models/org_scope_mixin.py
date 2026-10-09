from odoo import api, fields, models

ORG_LEVELS = ('division', 'business_unit', 'location', 'department')


class OrgScopeMixin(models.AbstractModel):
    """Link records to the organisation hierarchy so they can be scoped.

    Inherit this mixin on any model whose records should follow the users'
    Organisation scoping (``res.users`` "scope all apps" and App Specific
    Scoping). Setting a lower level fills in every level above it; changing
    a higher level clears the levels below that no longer belong to it.
    Records with no Division are not restricted by scoping.
    """
    _name = 'org.scope.mixin'
    _description = 'Organisation Scope Mixin'

    # Read by ir.rule._compute_domain to decide which models get scoped.
    _org_scoped = True

    org_division_id = fields.Many2one(
        comodel_name='org.division',
        string='Division',
        index=True,
        ondelete='restrict',
        compute='_compute_org_division_id',
        store=True,
        readonly=False,
        precompute=True,
    )
    org_business_unit_id = fields.Many2one(
        comodel_name='org.business.unit',
        string='Business Unit',
        index=True,
        ondelete='restrict',
        domain="[('division_id', '=?', org_division_id)]",
        compute='_compute_org_business_unit_id',
        store=True,
        readonly=False,
        precompute=True,
    )
    org_location_id = fields.Many2one(
        comodel_name='org.location',
        string='Location',
        index=True,
        ondelete='restrict',
        domain="[('business_unit_id', '=?', org_business_unit_id)]",
        compute='_compute_org_location_id',
        store=True,
        readonly=False,
        precompute=True,
    )
    org_department_id = fields.Many2one(
        comodel_name='org.department',
        string='Department',
        index=True,
        ondelete='restrict',
        domain="[('location_id', '=?', org_location_id)]",
    )

    @api.depends('org_department_id.location_id')
    def _compute_org_location_id(self):
        for rec in self:
            if rec.org_department_id:
                rec.org_location_id = rec.org_department_id.location_id
            else:
                rec.org_location_id = rec.org_location_id

    @api.depends('org_location_id.business_unit_id')
    def _compute_org_business_unit_id(self):
        for rec in self:
            if rec.org_location_id:
                rec.org_business_unit_id = rec.org_location_id.business_unit_id
            else:
                rec.org_business_unit_id = rec.org_business_unit_id

    @api.depends('org_business_unit_id.division_id')
    def _compute_org_division_id(self):
        for rec in self:
            if rec.org_business_unit_id:
                rec.org_division_id = rec.org_business_unit_id.division_id
            else:
                rec.org_division_id = rec.org_division_id

    @api.onchange('org_division_id')
    def _onchange_org_division_id(self):
        for rec in self:
            if rec.org_business_unit_id.division_id != rec.org_division_id:
                rec.org_business_unit_id = False

    @api.onchange('org_business_unit_id')
    def _onchange_org_business_unit_id(self):
        for rec in self:
            if rec.org_location_id.business_unit_id != rec.org_business_unit_id:
                rec.org_location_id = False

    @api.onchange('org_location_id')
    def _onchange_org_location_id(self):
        for rec in self:
            if rec.org_department_id.location_id != rec.org_location_id:
                rec.org_department_id = False

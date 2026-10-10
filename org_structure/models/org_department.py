from odoo import api, fields, models


class OrgDepartment(models.Model):
    _name = 'org.department'
    _description = 'Organisation Department'
    _inherit = ['org.unit.mixin']
    _order = 'company_id, division_id, business_unit_id, location_id, sequence, name'
    _check_company_auto = True
    _org_level = 'department'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    location_id = fields.Many2one(
        comodel_name='org.location',
        string='Location',
        index=True,
        ondelete='restrict',
    )
    # Inherited from the parent unit; set directly when it is the parent.
    business_unit_id = fields.Many2one(
        comodel_name='org.business.unit',
        string='Business Unit',
        index=True,
        ondelete='restrict',
        compute='_compute_business_unit_id',
        store=True,
        readonly=False,
        precompute=True,
    )
    division_id = fields.Many2one(
        comodel_name='org.division',
        string='Division',
        index=True,
        ondelete='restrict',
        compute='_compute_division_id',
        store=True,
        readonly=False,
        precompute=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        index=True,
        compute='_compute_company_id',
        store=True,
        readonly=False,
        precompute=True,
    )
    manager_id = fields.Many2one(comodel_name='res.users', string='Manager')
    note = fields.Html()

    _name_location_uniq = models.Constraint(
        'unique(name, location_id)',
        'A department with this name already exists in this location.',
    )

    @api.depends('location_id.business_unit_id')
    def _compute_business_unit_id(self):
        for rec in self:
            if rec.location_id:
                rec.business_unit_id = rec.location_id.business_unit_id
            else:
                rec.business_unit_id = rec.business_unit_id

    @api.depends('location_id.division_id', 'business_unit_id.division_id')
    def _compute_division_id(self):
        for rec in self:
            if rec.location_id:
                rec.division_id = rec.location_id.division_id
            elif rec.business_unit_id:
                rec.division_id = rec.business_unit_id.division_id
            else:
                rec.division_id = rec.division_id

    @api.depends('location_id.company_id', 'business_unit_id.company_id', 'division_id.company_id')
    def _compute_company_id(self):
        for rec in self:
            rec.company_id = rec._org_company_from_links() or rec.company_id or self.env.company

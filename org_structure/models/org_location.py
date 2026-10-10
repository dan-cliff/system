from odoo import api, fields, models


class OrgLocation(models.Model):
    _name = 'org.location'
    _description = 'Organisation Location'
    _inherit = ['org.unit.mixin']
    _order = 'company_id, division_id, business_unit_id, sequence, name'
    _check_company_auto = True
    _org_level = 'location'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    business_unit_id = fields.Many2one(
        comodel_name='org.business.unit',
        string='Business Unit',
        index=True,
        ondelete='restrict',
    )
    # Inherited from the parent unit; set directly when it is the parent.
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
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Address',
        check_company=True,
    )
    department_ids = fields.One2many(
        comodel_name='org.department',
        inverse_name='location_id',
        string='Departments',
    )
    department_count = fields.Integer(compute='_compute_department_count')
    note = fields.Html()

    _name_business_unit_uniq = models.Constraint(
        'unique(name, business_unit_id)',
        'A location with this name already exists in this business unit.',
    )

    @api.depends('business_unit_id.division_id')
    def _compute_division_id(self):
        for rec in self:
            if rec.business_unit_id:
                rec.division_id = rec.business_unit_id.division_id
            else:
                rec.division_id = rec.division_id

    @api.depends('business_unit_id.company_id', 'division_id.company_id')
    def _compute_company_id(self):
        for rec in self:
            rec.company_id = rec._org_company_from_links() or rec.company_id or self.env.company

    def _compute_department_count(self):
        for rec in self:
            rec.department_count = len(rec.department_ids)

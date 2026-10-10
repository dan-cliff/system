from odoo import api, fields, models


class OrgBusinessUnit(models.Model):
    _name = 'org.business.unit'
    _description = 'Business Unit'
    _inherit = ['org.unit.mixin']
    _order = 'company_id, division_id, sequence, name'
    _check_company_auto = True
    _org_level = 'business_unit'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    division_id = fields.Many2one(
        comodel_name='org.division',
        string='Division',
        index=True,
        ondelete='restrict',
    )
    # Inherited from the parent unit; set directly when there is none.
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
    location_ids = fields.One2many(
        comodel_name='org.location',
        inverse_name='business_unit_id',
        string='Locations',
    )
    location_count = fields.Integer(compute='_compute_location_count')
    note = fields.Html()

    _name_division_uniq = models.Constraint(
        'unique(name, division_id)',
        'A business unit with this name already exists in this division.',
    )

    @api.depends('division_id.company_id')
    def _compute_company_id(self):
        for rec in self:
            rec.company_id = rec._org_company_from_links() or rec.company_id or self.env.company

    def _compute_location_count(self):
        for rec in self:
            rec.location_count = len(rec.location_ids)

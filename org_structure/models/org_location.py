from odoo import fields, models


class OrgLocation(models.Model):
    _name = 'org.location'
    _description = 'Organisation Location'
    _order = 'company_id, division_id, business_unit_id, sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    business_unit_id = fields.Many2one(
        comodel_name='org.business.unit',
        string='Business Unit',
        required=True,
        index=True,
        ondelete='restrict',
    )
    # Inherited from the direct parent.
    division_id = fields.Many2one(
        related='business_unit_id.division_id',
        store=True,
        index=True,
        precompute=True,
    )
    company_id = fields.Many2one(
        related='business_unit_id.company_id',
        store=True,
        index=True,
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

    def _compute_department_count(self):
        for rec in self:
            rec.department_count = len(rec.department_ids)

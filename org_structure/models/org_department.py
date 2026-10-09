from odoo import fields, models


class OrgDepartment(models.Model):
    _name = 'org.department'
    _description = 'Organisation Department'
    _order = 'company_id, division_id, business_unit_id, location_id, sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    location_id = fields.Many2one(
        comodel_name='org.location',
        string='Location',
        required=True,
        index=True,
        ondelete='restrict',
    )
    # Inherited from the direct parent.
    business_unit_id = fields.Many2one(
        related='location_id.business_unit_id',
        store=True,
        index=True,
        precompute=True,
    )
    division_id = fields.Many2one(
        related='location_id.division_id',
        store=True,
        index=True,
        precompute=True,
    )
    company_id = fields.Many2one(
        related='location_id.company_id',
        store=True,
        index=True,
        precompute=True,
    )
    manager_id = fields.Many2one(comodel_name='res.users', string='Manager')
    note = fields.Html()

    _name_location_uniq = models.Constraint(
        'unique(name, location_id)',
        'A department with this name already exists in this location.',
    )

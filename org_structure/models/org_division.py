from odoo import fields, models


class OrgDivision(models.Model):
    _name = 'org.division'
    _description = 'Division'
    _order = 'company_id, sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    manager_id = fields.Many2one(comodel_name='res.users', string='Manager')
    business_unit_ids = fields.One2many(
        comodel_name='org.business.unit',
        inverse_name='division_id',
        string='Business Units',
    )
    business_unit_count = fields.Integer(compute='_compute_business_unit_count')
    note = fields.Html()

    _name_company_uniq = models.Constraint(
        'unique(name, company_id)',
        'A division with this name already exists in this company.',
    )

    def _compute_business_unit_count(self):
        for rec in self:
            rec.business_unit_count = len(rec.business_unit_ids)

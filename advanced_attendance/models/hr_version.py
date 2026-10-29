from odoo import api, fields, models


class HrVersion(models.Model):
    _inherit = 'hr.version'

    @api.model
    def _domain_onsite_ruleset(self):
        return ['|', ('country_id', '=', False), ('country_id', 'in', self.env.companies.country_id.ids)]

    # Prefixed with onsite_ so it never clashes with Odoo's Attendances app.
    onsite_ruleset_id = fields.Many2one(
        'advanced.attendance.overtime.ruleset', string='Overtime Ruleset',
        domain=_domain_onsite_ruleset, tracking=True,
        groups='advanced_attendance.group_onsite_admin',
        default=lambda self: self.env.ref('advanced_attendance.onsite_default_ruleset', raise_if_not_found=False),
        help='The On Site overtime rules that decide which hours count as extra hours.',
    )

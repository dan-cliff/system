import datetime
from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval


class EmployeeHealthcareIndicator(models.Model):
    _name = 'employee.healthcare.indicator'
    _description = 'Healthcare Indicator'
    _order = 'sequence, name'

    name = fields.Char(string='Indicator', required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(
        string='Colour', default=0,
        help='Colour index (0–11) used for the indicator badge on the employee.',
    )
    description = fields.Text(string='Description')
    match_mode = fields.Selection([
        ('any', 'Any rule matches (OR)'),
        ('all', 'All rules match (AND)'),
    ], string='Match Mode', default='any', required=True,
        help='OR: indicator activates when at least one rule is satisfied.\n'
             'AND: indicator activates only when every rule is satisfied.',
    )
    rule_ids = fields.One2many(
        'employee.healthcare.indicator.rule', 'indicator_id', string='Rules',
    )
    active = fields.Boolean(default=True)
    employee_count = fields.Integer(
        string='Employees', compute='_compute_employee_count',
    )

    def _compute_employee_count(self):
        for ind in self:
            ind.employee_count = self.env['employee.healthcare'].sudo().search_count(
                [('healthcare_indicator_ids', 'in', ind.id)]
            )

    def _matches(self, employee):
        """Return True if this indicator should be active for the given employee.healthcare record."""
        self.ensure_one()
        if not self.rule_ids:
            return False
        results = [rule._evaluate(employee) for rule in self.rule_ids]
        if self.match_mode == 'all':
            return all(results)
        return any(results)

    # ── Re-evaluate all healthcare records when indicators or rules change ──

    @api.model_create_multi
    def create(self, vals_list):
        indicators = super().create(vals_list)
        indicators._reeval_all_employees()
        return indicators

    def write(self, vals):
        result = super().write(vals)
        self._reeval_all_employees()
        return result

    def unlink(self):
        # Capture records before deletion so we can reeval after
        healthcare_records = self.env['employee.healthcare'].sudo().search([])
        result = super().unlink()
        healthcare_records.action_evaluate_healthcare_indicators()
        return result

    def _reeval_all_employees(self):
        """Re-evaluate every healthcare record against the current active indicators."""
        self.env['employee.healthcare'].sudo().search([]).action_evaluate_healthcare_indicators()

    def action_reeval_all_employees(self):
        """Manual button: re-evaluate all healthcare records against all indicators."""
        self._reeval_all_employees()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Indicators Re-evaluated',
                'message': 'All employee healthcare indicators have been refreshed.',
                'type': 'success',
                'sticky': False,
            },
        }

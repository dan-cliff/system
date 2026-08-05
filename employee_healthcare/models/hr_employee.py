from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # ── Healthcare record link ─────────────────────────────────────────────
    # No groups restriction on the One2many — needed for the compute trigger
    # to fire regardless of the calling user's group membership.
    healthcare_ids = fields.One2many(
        'employee.healthcare', 'employee_id',
        string='Healthcare Records',
    )
    healthcare_id = fields.Many2one(
        'employee.healthcare',
        string='Healthcare Record',
        compute='_compute_healthcare_id',
        store=True,
        groups='employee_healthcare.group_employee_healthcare_employee',
    )

    # ── Indicator tags (convenience related field for the employee form) ───
    healthcare_indicator_ids = fields.Many2many(
        'employee.healthcare.indicator',
        related='healthcare_id.healthcare_indicator_ids',
        string='Healthcare Indicators',
        groups='employee_healthcare.group_employee_healthcare_employee',
    )

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        # Auto-create a healthcare record for every new employee so the two
        # tables remain in sync at all times.
        HealthcareRecord = self.env['employee.healthcare'].sudo()
        HealthcareRecord.create([{'employee_id': emp.id} for emp in employees])
        return employees

    @api.depends('healthcare_ids')
    def _compute_healthcare_id(self):
        for employee in self:
            employee.healthcare_id = employee.healthcare_ids[:1]

    def action_print_care_profile(self):
        """Download the employee Care Profile PDF directly, skipping any wizard."""
        self.ensure_one()
        record = self.env['employee.healthcare'].sudo().search(
            [('employee_id', '=', self.id)], limit=1
        )
        if not record:
            record = self.env['employee.healthcare'].sudo().create(
                {'employee_id': self.id}
            )
        return self.env.ref(
            'employee_healthcare.action_report_employee_care_profile'
        ).report_action(record, config=False)

    def action_open_healthcare_record(self):
        """Open (or create) this employee's healthcare record in a form view."""
        self.ensure_one()
        record = self.env['employee.healthcare'].sudo().search(
            [('employee_id', '=', self.id)], limit=1
        )
        if not record:
            record = self.env['employee.healthcare'].sudo().create(
                {'employee_id': self.id}
            )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Healthcare Record',
            'res_model': 'employee.healthcare',
            'res_id': record.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

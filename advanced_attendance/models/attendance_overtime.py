# Ported from Odoo 19 hr_attendance (LGPL-3), on On Site's models.
from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class AdvancedAttendanceOvertimeLine(models.Model):
    _name = 'advanced.attendance.overtime.line'
    _description = 'Extra Hours'
    _rec_name = 'employee_id'
    _order = 'time_start'

    employee_id = fields.Many2one(
        'hr.employee', string="Employee",
        required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='employee_id.company_id', store=True)

    date = fields.Date(string='Day', index=True, required=True)
    status = fields.Selection([
            ('to_approve', "To Approve"),
            ('approved', "Approved"),
            ('refused', "Refused")
        ],
        compute='_compute_status',
        required=True, store=True, readonly=False, precompute=True,
    )
    duration = fields.Float(string='Extra Hours', default=0.0, required=True)
    manual_duration = fields.Float(  # TODO -> real_duration for easier upgrade
        string='Extra Hours (encoded)',
        compute='_compute_manual_duration',
        store=True, readonly=False,
    )

    time_start = fields.Datetime(string='Start')  # time_start will be equal to attendance.check_in
    time_stop = fields.Datetime(string='Stop')  # time_stop will be equal to attendance.check_out
    amount_rate = fields.Float("Overtime pay rate", required=True, default=1.0)

    is_manager = fields.Boolean(compute="_compute_is_manager")

    rule_ids = fields.Many2many(
        "advanced.attendance.overtime.rule", "advanced_attendance_overtime_line_rule_rel", "line_id", "rule_id",
        string="Applied Rules",
    )

    # in payroll: rate, work_entry_type
    # in time_off: convertible_to_time_off

    # Check no overlapping overtimes for the same employee.
    # Technical explanation: Exclude constraints compares the given expression on rows 2 by 2 using the given operator; && on tsrange is the intersection.
    # cf: https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-EXCLUSION
    # for employee_id we compare [employee_id -> employee_id] ranges bc raw integer is not supported (?)
    # _overtime_no_overlap_same_employee = models.Constraint("""
    #     EXCLUDE USING GIST (
    #         tsrange(time_start, time_stop, '()') WITH &&,
    #         int4range(employee_id, employee_id, '[]') WITH =
    #     )
    #     """,
    #     "Employee cannot have overlapping overtimes",
    # )
    _overtime_start_before_end = models.Constraint(
        'CHECK (time_stop > time_start)',
        'Starting time should be before end time.',
    )

    @api.depends('employee_id')
    def _compute_status(self):
        for overtime in self:
            if not overtime.status:
                overtime.status = 'to_approve' if overtime.employee_id.company_id.onsite_overtime_validation == 'by_manager' else 'approved'

    @api.depends('duration')
    def _compute_manual_duration(self):
        for overtime in self:
            overtime.manual_duration = overtime.duration

    @api.depends_context('uid')
    def _compute_is_manager(self):
        can_approve = self.env.user.has_group('advanced_attendance.group_attendance_approve')
        for overtime in self:
            overtime.is_manager = can_approve

    def _check_can_approve(self):
        if not self.env.su and not self.env.user.has_group('advanced_attendance.group_attendance_approve'):
            raise AccessError(_('You are not allowed to approve or refuse extra hours.'))
        # Only the extra hours of attendances they can see.
        self.check_access('read')

    def action_approve(self):
        self._check_can_approve()
        self.sudo().write({'status': 'approved'})

    def action_refuse(self):
        self._check_can_approve()
        self.sudo().write({'status': 'refused'})

    def _linked_attendances(self):
        return self.env['advanced.attendance'].search([
            ('check_in', 'in', self.mapped('time_start')),
            ('employee_id', 'in', self.employee_id.ids),
        ])

    def write(self, vals):
        if any(key in vals for key in ['status', 'manual_duration', 'duration']):
            attendances = self._linked_attendances()
            if any(key in vals for key in ['status', 'manual_duration']):
                self.env.add_to_compute(
                    attendances._fields['overtime_status'],
                    attendances
                )
                self.env.add_to_compute(
                    attendances._fields['validated_overtime_hours'],
                    attendances
                )
            if 'duration' in vals:
                self.env.add_to_compute(
                    attendances._fields['overtime_hours'],
                    attendances
                )
                self.env.add_to_compute(
                    attendances._fields['expected_hours'],
                    attendances
                )
        return super().write(vals)

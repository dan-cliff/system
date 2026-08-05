from odoo import models, fields, api, _


class LmsCourseGroup(models.Model):
    _name = 'lms.course.group'
    _description = 'LMS Course Group (Training Package)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Package Name', required=True, translate=True, tracking=True)
    code = fields.Char(string='Code', copy=False)
    description = fields.Html(string='Description', sanitize=True)
    color = fields.Integer(string='Colour', default=0)
    active = fields.Boolean(default=True)
    image = fields.Image(string='Thumbnail', max_width=256, max_height=256)

    course_ids = fields.Many2many(
        'lms.course',
        'lms_course_group_course_rel',
        'group_id',
        'course_id',
        string='Courses',
    )
    course_count = fields.Integer(string='Courses', compute='_compute_course_count')

    assignment_ids = fields.One2many('lms.course.group.assignment', 'course_group_id', string='Assignments')
    assignment_count = fields.Integer(string='Assignments', compute='_compute_assignment_count')

    @api.depends('course_ids')
    def _compute_course_count(self):
        for rec in self:
            rec.course_count = len(rec.course_ids)

    def _compute_assignment_count(self):
        for rec in self:
            rec.assignment_count = len(rec.assignment_ids)

    def action_view_assignments(self):
        self.ensure_one()
        return {
            'name': _('Assignments — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'lms.course.group.assignment',
            'view_mode': 'list,form',
            'domain': [('course_group_id', '=', self.id)],
            'context': {'default_course_group_id': self.id},
        }


class LmsCourseGroupAssignment(models.Model):
    _name = 'lms.course.group.assignment'
    _description = 'LMS Course Group Assignment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_assigned desc'

    name = fields.Char(
        string='Package Name',
        related='course_group_id.name',
        store=False,
    )

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade', tracking=True
    )
    course_group_id = fields.Many2one(
        'lms.course.group', string='Training Package', required=True, ondelete='cascade', tracking=True
    )
    assigned_by = fields.Many2one(
        'res.users', string='Assigned By',
        default=lambda self: self.env.user,
        readonly=True,
    )
    date_assigned = fields.Date(
        string='Date Assigned', default=fields.Date.today, required=True
    )
    due_date = fields.Date(string='Due Date', tracking=True)
    notes = fields.Text(string='Notes')

    state = fields.Selection([
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ], string='Status', compute='_compute_state', store=True)

    record_ids = fields.One2many(
        'lms.employee.record', 'assignment_id', string='Course Records'
    )
    record_count = fields.Integer(string='Records', compute='_compute_record_counts', store=True)
    completed_count = fields.Integer(string='Completed', compute='_compute_record_counts', store=True)
    progress = fields.Integer(string='Progress (%)', compute='_compute_record_counts', store=True)

    @api.depends('record_ids', 'record_ids.state')
    def _compute_record_counts(self):
        for rec in self:
            total = len(rec.record_ids)
            completed = len(rec.record_ids.filtered(lambda r: r.state == 'completed'))
            rec.record_count = total
            rec.completed_count = completed
            rec.progress = int(completed / total * 100) if total else 0

    @api.depends('record_count', 'completed_count')
    def _compute_state(self):
        for rec in self:
            rec.state = (
                'completed'
                if rec.record_count and rec.record_count == rec.completed_count
                else 'in_progress'
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for assignment in records:
            assignment._create_employee_records()
        return records

    def _create_employee_records(self):
        """Auto-create an lms.employee.record for each course in the package."""
        self.ensure_one()
        existing_courses = self.record_ids.mapped('course_id')
        for course in self.course_group_id.course_ids:
            if course not in existing_courses:
                self.env['lms.employee.record'].create({
                    'employee_id': self.employee_id.id,
                    'course_id': course.id,
                    'assignment_id': self.id,
                })

    def action_view_records(self):
        self.ensure_one()
        return {
            'name': _('Course Records'),
            'type': 'ir.actions.act_window',
            'res_model': 'lms.employee.record',
            'view_mode': 'list,form',
            'domain': [('assignment_id', '=', self.id)],
            'context': {'default_assignment_id': self.id},
        }

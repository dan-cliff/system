from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class LmsCourseSession(models.Model):
    _name = 'lms.course.session'
    _description = 'LMS Course Session (In-Person)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc'

    name = fields.Char(string='Session Name', required=True, tracking=True)
    course_id = fields.Many2one('lms.course', string='Course', required=True, ondelete='cascade', tracking=True)
    course_type = fields.Selection(related='course_id.course_type', store=True)

    date_start = fields.Datetime(string='Start Date & Time', required=True, tracking=True)
    date_end = fields.Datetime(string='End Date & Time', required=True, tracking=True)
    location = fields.Char(string='Location / Venue', tracking=True)

    instructor_id = fields.Many2one(
        'hr.employee',
        string='Instructor / Facilitator',
        ondelete='set null',
    )
    instructor_name = fields.Char(string='External Instructor Name')

    max_capacity = fields.Integer(string='Maximum Capacity', default=20)
    enrolled_count = fields.Integer(string='Enrolled', compute='_compute_enrolled_count', store=True)
    available_seats = fields.Integer(string='Seats Available', compute='_compute_enrolled_count', store=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('open', 'Open for Enrolment'),
        ('full', 'Full'),
        ('closed', 'Closed for Enrolment'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)

    is_public = fields.Boolean(
        string='Allow Self-Enrolment',
        help='When enabled, employees can self-enrol via the employee portal.',
        default=True,
    )
    requires_approval = fields.Boolean(
        string='Require Manager Approval for Self-Enrolment',
        default=True,
        help='When an employee self-enrolls, their manager must approve before the enrolment is confirmed.',
    )

    enrollment_ids = fields.One2many('lms.session.enrollment', 'session_id', string='Enrolments')
    notes = fields.Html(string='Notes / Instructions')

    @api.depends('enrollment_ids', 'enrollment_ids.state', 'max_capacity')
    def _compute_enrolled_count(self):
        for rec in self:
            confirmed = rec.enrollment_ids.filtered(
                lambda e: e.state in ('confirmed', 'attended')
            )
            rec.enrolled_count  = len(confirmed)
            rec.available_seats = max(0, rec.max_capacity - rec.enrolled_count)
            # Auto-close when the session is open/full and capacity is reached
            if rec.state == 'open' and rec.available_seats == 0:
                rec.state = 'closed'
            elif rec.state == 'closed' and rec.available_seats > 0:
                rec.state = 'open'

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_end and rec.date_start and rec.date_end <= rec.date_start:
                raise ValidationError(_('End date must be after start date.'))

    def action_open(self):
        for rec in self:
            if rec.max_capacity > 0 and rec.enrolled_count >= rec.max_capacity:
                raise ValidationError(_(
                    "Cannot open '%(session)s' for enrolment \u2014 maximum capacity of %(cap)d "
                    "has already been reached.\n\n"
                    "To resolve this, either increase the Maximum Capacity or create a new "
                    "Training Session.",
                    session=rec.name,
                    cap=rec.max_capacity,
                ))
            rec.state = 'open'

    def action_close_enrolment(self):
        """Manually close a session for further enrolment."""
        for rec in self:
            if rec.state == 'open':
                rec.state = 'closed'

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_complete(self):
        """Mark session complete and auto-update employee records."""
        self.ensure_one()
        self.write({'state': 'completed'})
        for enrollment in self.enrollment_ids.filtered(lambda e: e.state == 'confirmed'):
            enrollment.write({'state': 'attended'})
            # Create / update employee record
            record = self.env['lms.employee.record'].search([
                ('employee_id', '=', enrollment.employee_id.id),
                ('course_id', '=', self.course_id.id),
                ('session_enrollment_id', '=', enrollment.id),
            ], limit=1)
            if not record:
                record = self.env['lms.employee.record'].create({
                    'employee_id': enrollment.employee_id.id,
                    'course_id': self.course_id.id,
                    'session_enrollment_id': enrollment.id,
                })
            record._mark_completed()

    @api.model
    def get_sessions_report_data(self, domain=None):
        """Return flat list of sessions for the Sessions report.

        Records are ordered by date_start ASC (upcoming first).
        """
        records = self.search(domain or [], order='date_start asc')
        result = []
        for rec in records:
            instructor = rec.instructor_id.name or rec.instructor_name or ''
            result.append({
                'id':              rec.id,
                'name':            rec.name,
                'course_id':       rec.course_id.id,
                'course_name':     rec.course_id.name or '',
                'date_start':      rec.date_start.strftime('%Y-%m-%dT%H:%M') if rec.date_start else False,
                'date_end':        rec.date_end.strftime('%Y-%m-%dT%H:%M')   if rec.date_end   else False,
                'location':        rec.location or '',
                'instructor':      instructor,
                'max_capacity':    rec.max_capacity,
                'enrolled_count':  rec.enrolled_count,
                'available_seats': rec.available_seats,
                'state':           rec.state,
                'is_public':       rec.is_public,
            })
        return result

    def action_view_enrollments(self):
        self.ensure_one()
        return {
            'name': _('Enrolments — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'lms.session.enrollment',
            'view_mode': 'list,form',
            'domain': [('session_id', '=', self.id)],
            'context': {'default_session_id': self.id},
        }

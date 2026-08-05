from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta


class LmsEmployeeRecord(models.Model):
    _name = 'lms.employee.record'
    _description = 'LMS Employee Course Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'employee_id, course_id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade', tracking=True
    )
    user_id = fields.Many2one(
        'res.users', string='User', related='employee_id.user_id', store=True, readonly=True
    )
    course_id = fields.Many2one(
        'lms.course', string='Course', required=True, ondelete='cascade', tracking=True
    )
    assignment_id = fields.Many2one(
        'lms.course.group.assignment', string='Package Assignment',
        ondelete='set null', tracking=True
    )
    session_enrollment_id = fields.Many2one(
        'lms.session.enrollment', string='Session Enrolment',
        ondelete='set null',
    )

    name = fields.Char(
        string='Record',
        compute='_compute_name',
        store=True,
    )

    # Course metadata (denormalised for quick access)
    course_type = fields.Selection(related='course_id.course_type', store=True, string='Type')
    delivery_mode = fields.Selection(related='course_id.delivery_mode', store=True, string='Delivery')

    state = fields.Selection([
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('pending_upload', 'Pending Upload'),
        ('pending_verification', 'Pending Verification'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
        ('lapsed', 'Lapsed'),
    ], string='Status', default='not_started', required=True, tracking=True)

    start_date = fields.Date(string='Started On', tracking=True)
    completion_date = fields.Date(string='Completed On', tracking=True)
    expiry_date = fields.Date(string='Expires On', tracking=True)

    # eLearning / SCORM progress
    score = fields.Float(string='Score (%)', digits=(5, 2))
    passed = fields.Boolean(string='Passed', tracking=True)
    scorm_completion_status = fields.Char(string='SCORM Completion Status')
    scorm_data = fields.Text(string='SCORM Runtime Data (JSON)', help='Raw SCORM cmi data.')

    # Google Slides progress
    slides_max_page = fields.Integer(
        string='Furthest Slide Viewed',
        default=0,
        help='The highest slide number this employee has navigated to. '
             'Completion is blocked until this reaches the course slide_count.',
    )

    # Uploads (licence/qualification proof, certificates)
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'lms_record_attachment_rel',
        'record_id',
        'attachment_id',
        string='Uploaded Documents / Certificates',
    )
    attachment_count = fields.Integer(string='Documents', compute='_compute_attachment_count')

    notes = fields.Text(string='Notes')

    # Assessments
    assessment_ids = fields.One2many('lms.assessment', 'employee_record_id', string='Assessments')
    assessment_count = fields.Integer(compute='_compute_assessment_count', string='Assessments')

    # Verification
    verified_by = fields.Many2one('res.users', string='Verified By', readonly=True)
    verified_date = fields.Date(string='Verified On', readonly=True)

    @api.depends('employee_id.name', 'course_id.name')
    def _compute_name(self):
        for rec in self:
            emp    = rec.employee_id.name or '(No Employee)'
            course = rec.course_id.name   or '(No Course)'
            rec.name = f"{emp} — {course}"

    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        for rec in self:
            rec.attachment_count = len(rec.attachment_ids)

    @api.depends('assessment_ids')
    def _compute_assessment_count(self):
        for rec in self:
            rec.assessment_count = len(rec.assessment_ids)

    def action_view_assessments(self):
        self.ensure_one()
        ctx = {'default_employee_record_id': self.id}
        if self.course_id.assessment_template_id:
            ctx['default_template_id'] = self.course_id.assessment_template_id.id
        return {
            'name': _('Assessments — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'lms.assessment',
            'view_mode': 'list,form',
            'domain': [('employee_record_id', '=', self.id)],
            'context': ctx,
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.delivery_mode == 'upload':
                rec.state = 'pending_upload'
        return records

    def _mark_completed(self):
        """Internal helper to mark a record complete and compute expiry."""
        self.ensure_one()
        if self.course_id.requires_assessment and self.course_id.assessment_template_id:
            passed = any(a.state == 'passed' and a.passed for a in self.assessment_ids)
            if not passed:
                raise UserError(_(
                    'This course requires a passing assessment before it can be marked complete. '
                    'Please complete and pass the assessment "%s" first.'
                ) % self.course_id.assessment_template_id.name)
        today = fields.Date.today()
        validity = self.course_id.validity_months
        expiry = (
            today + relativedelta(months=validity) if validity else False
        )
        self.write({
            'state': 'completed',
            'completion_date': today,
            'expiry_date': expiry,
            'passed': True,
        })
        self._lapse_older_records()

    def _lapse_older_records(self):
        """Lapse any earlier training records for the same employee + course.

        After this record is completed, any other record for the same
        employee/course whose start, completion, or expiry date is earlier
        than the corresponding date on *this* record is considered superseded
        and is moved to the 'lapsed' state.
        """
        self.ensure_one()

        # Collect OR clauses for whichever date fields are populated
        or_clauses = []
        for fname, val in [
            ('start_date',      self.start_date),
            ('completion_date', self.completion_date),
            ('expiry_date',     self.expiry_date),
        ]:
            if val:
                or_clauses.append((fname, '<', val))

        if not or_clauses:
            return

        # Build Odoo prefix-OR domain
        if len(or_clauses) == 1:
            date_domain = [or_clauses[0]]
        elif len(or_clauses) == 2:
            date_domain = ['|', or_clauses[0], or_clauses[1]]
        else:
            date_domain = ['|', '|', or_clauses[0], or_clauses[1], or_clauses[2]]

        older = self.search([
            ('id',          '!=', self.id),
            ('employee_id', '=',  self.employee_id.id),
            ('course_id',   '=',  self.course_id.id),
            ('state',       '!=', 'lapsed'),
        ] + date_domain)

        if older:
            older.write({'state': 'lapsed'})
            for rec in older:
                rec.message_post(
                    body=_('This record has been lapsed — superseded by a newer training completion.')
                )

    def action_start(self):
        """Employee begins the course."""
        for rec in self:
            if rec.state == 'not_started':
                rec.write({'state': 'in_progress', 'start_date': fields.Date.today()})

    def action_mark_complete(self):
        """Manually mark a record complete (admin / manager action)."""
        for rec in self:
            rec._mark_completed()

    def action_verify(self):
        """Verify an uploaded licence/qualification document."""
        for rec in self:
            if rec.state not in ('pending_upload', 'pending_verification'):
                raise UserError(_('Only records pending upload or verification can be verified.'))
            if not rec.attachment_ids:
                raise UserError(_('No documents have been uploaded yet.'))
            if rec.course_id.requires_assessment and rec.course_id.assessment_template_id:
                passed = any(a.state == 'passed' and a.passed for a in rec.assessment_ids)
                if not passed:
                    raise UserError(_(
                        'This course requires a passing assessment before it can be marked complete. '
                        'Please complete and pass the assessment "%s" first.'
                    ) % rec.course_id.assessment_template_id.name)
            rec.write({
                'state': 'completed',
                'completion_date': fields.Date.today(),
                'expiry_date': (
                    fields.Date.today() + relativedelta(months=rec.course_id.validity_months)
                    if rec.course_id.validity_months else False
                ),
                'passed': True,
                'verified_by': self.env.user.id,
                'verified_date': fields.Date.today(),
            })
            rec._lapse_older_records()

    def action_fail(self):
        for rec in self:
            rec.write({'state': 'failed', 'passed': False})

    def action_lapse(self):
        """Manually mark a record as lapsed (competency no longer maintained)."""
        for rec in self:
            rec.write({'state': 'lapsed'})

    def action_print_training_record(self):
        """Return the Training Record PDF report action for this record."""
        return self.env.ref(
            'learning_management.action_lms_training_record_pdf'
        ).report_action(self)

    def action_reset(self):
        for rec in self:
            rec.write({
                'state': 'not_started',
                'start_date': False,
                'completion_date': False,
                'score': 0.0,
                'passed': False,
                'scorm_completion_status': False,
                'scorm_data': False,
            })

    @api.model
    def _cron_check_expiry(self):
        """Nightly cron: mark records expired when past the expiry date."""
        today = fields.Date.today()
        expired = self.search([
            ('state', '=', 'completed'),
            ('expiry_date', '<', today),
            ('expiry_date', '!=', False),
        ])
        expired.write({'state': 'expired'})

    @api.model
    def get_tna_matrix_data(self, domain=None):
        """Return data for the Training Needs Analysis matrix view.

        Returns a dict with:
          employees  – list of {id, name} dicts, sorted by name (matrix columns)
          courses    – list of {id, name, code, course_type} dicts, sorted by name (matrix rows)
          cells      – dict keyed by "<employee_id>_<course_id>" containing record state/dates
        """
        records = self.search(domain or [])

        employees = {}
        courses = {}
        cells = {}

        for rec in records:
            emp = rec.employee_id
            course = rec.course_id

            if emp.id not in employees:
                employees[emp.id] = {'id': emp.id, 'name': emp.name}
            if course.id not in courses:
                courses[course.id] = {
                    'id': course.id,
                    'name': course.name,
                    'code': course.code or '',
                    'course_type': course.course_type,
                }

            key = f"{emp.id}_{course.id}"
            cells[key] = {
                'id': rec.id,
                'state': rec.state,
                'completion_date': rec.completion_date and rec.completion_date.isoformat() or False,
                'expiry_date': rec.expiry_date and rec.expiry_date.isoformat() or False,
            }

        return {
            'employees': sorted(employees.values(), key=lambda e: e['name']),
            'courses': sorted(courses.values(), key=lambda c: c['name']),
            'cells': cells,
        }

    @api.model
    def get_expiring_report_data(self, domain=None):
        """Return flat list of training records for the Expiring report.

        Records are ordered by expiry_date ASC (nulls last), then employee, then course.
        """
        records = self.search(
            domain or [],
            order='expiry_date asc nulls last, employee_id, course_id',
        )
        result = []
        for rec in records:
            result.append({
                'id': rec.id,
                'employee_id': rec.employee_id.id,
                'employee_name': rec.employee_id.name or '',
                'department': rec.employee_id.department_id.name or '',
                'company': rec.employee_id.company_id.name or '',
                'course_id': rec.course_id.id,
                'course_name': rec.course_id.name or '',
                'course_code': rec.course_id.code or '',
                'course_type': rec.course_type or '',
                'state': rec.state,
                'start_date': rec.start_date and rec.start_date.isoformat() or False,
                'completion_date': rec.completion_date and rec.completion_date.isoformat() or False,
                'expiry_date': rec.expiry_date and rec.expiry_date.isoformat() or False,
            })
        return result

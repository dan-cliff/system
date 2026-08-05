from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class LmsAssessmentTemplate(models.Model):
    _name = 'lms.assessment.template'
    _description = 'LMS Assessment Template'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Name', required=True, tracking=True)
    delivery_type = fields.Selection([
        ('electronic', 'Electronic (Self-Service)'),
        ('assessor_checklist', 'Assessor Checklist'),
    ], string='Delivery Type', required=True, default='electronic',
        help='Electronic: delivered online to the employee. Assessor Checklist: assessor completes while observing.',
        tracking=True)
    description = fields.Html(string='Description', sanitize=True)
    question_ids = fields.One2many(
        'lms.assessment.question', 'template_id', string='Questions / Checklist Items'
    )
    question_count = fields.Integer(
        string='Questions', compute='_compute_question_count', store=True
    )
    passing_score = fields.Integer(
        string='Passing Score (%)', default=80,
        help='Minimum % to pass (applies to auto-scored electronic assessments).'
    )
    active = fields.Boolean(default=True)
    course_count = fields.Integer(
        string='Courses', compute='_compute_course_count'
    )

    @api.depends('question_ids')
    def _compute_question_count(self):
        for rec in self:
            rec.question_count = len(rec.question_ids)

    def _compute_course_count(self):
        for rec in self:
            rec.course_count = self.env['lms.course'].search_count(
                [('assessment_template_id', '=', rec.id)]
            )

    def action_view_courses(self):
        self.ensure_one()
        return {
            'name': _('Courses — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'lms.course',
            'view_mode': 'list,form',
            'domain': [('assessment_template_id', '=', self.id)],
            'context': {'default_assessment_template_id': self.id},
        }


class LmsAssessmentQuestion(models.Model):
    _name = 'lms.assessment.question'
    _description = 'LMS Assessment Question'
    _order = 'template_id, sequence, id'

    template_id = fields.Many2one(
        'lms.assessment.template', string='Template', required=True, ondelete='cascade'
    )
    sequence = fields.Integer(string='Sequence', default=10)
    question_type = fields.Selection([
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True / False'),
        ('short_text', 'Short Text Answer'),
        ('checklist_item', 'Checklist Item'),
    ], string='Type', required=True, default='multiple_choice')
    question_text = fields.Text(string='Question / Item', required=True)
    marks = fields.Integer(string='Marks', default=1,
                           help='Weight of this question in scoring.')
    option_ids = fields.One2many(
        'lms.assessment.question.option', 'question_id', string='Options'
    )
    correct_option_id = fields.Many2one(
        'lms.assessment.question.option', string='Correct Option',
        domain="[('question_id', '=', id)]"
    )
    correct_bool = fields.Boolean(
        string='Correct Answer (True/False)', default=True
    )

    @api.constrains('question_type', 'option_ids')
    def _check_multiple_choice_options(self):
        for rec in self:
            if rec.question_type == 'multiple_choice' and len(rec.option_ids) < 2:
                raise ValidationError(_(
                    'Multiple choice question "%s" must have at least 2 options.'
                ) % rec.question_text)


class LmsAssessmentQuestionOption(models.Model):
    _name = 'lms.assessment.question.option'
    _description = 'LMS Assessment Question Option'
    _rec_name = 'text'
    _order = 'question_id, sequence, id'

    question_id = fields.Many2one(
        'lms.assessment.question', string='Question', required=True, ondelete='cascade'
    )
    sequence = fields.Integer(string='Sequence', default=10)
    text = fields.Char(string='Option Text', required=True)


class LmsAssessment(models.Model):
    _name = 'lms.assessment'
    _description = 'LMS Assessment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Assessment', compute='_compute_name', store=True
    )
    template_id = fields.Many2one(
        'lms.assessment.template', string='Template',
        required=True, ondelete='restrict', tracking=True
    )
    delivery_type = fields.Selection(
        related='template_id.delivery_type', string='Delivery Type',
        store=True, readonly=True
    )
    employee_record_id = fields.Many2one(
        'lms.employee.record', string='Training Record',
        ondelete='cascade', tracking=True
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        related='employee_record_id.employee_id', store=True, readonly=True
    )
    course_id = fields.Many2one(
        'lms.course', string='Course',
        related='employee_record_id.course_id', store=True, readonly=True
    )
    assessor_id = fields.Many2one('res.users', string='Assessor')
    state = fields.Selection([
        ('draft', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted / Awaiting Review'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
    ], string='State', default='draft', required=True, tracking=True)
    answer_ids = fields.One2many(
        'lms.assessment.answer', 'assessment_id', string='Answers'
    )
    score = fields.Float(string='Score (%)', digits=(5, 2), tracking=True)
    passed = fields.Boolean(string='Passed', tracking=True)
    start_date = fields.Datetime(string='Started On', tracking=True)
    submit_date = fields.Datetime(string='Submitted On', tracking=True)
    notes = fields.Text(string='Assessor Notes')

    @api.depends('template_id.name', 'employee_id.name')
    def _compute_name(self):
        for rec in self:
            tmpl = rec.template_id.name or '(No Template)'
            emp = rec.employee_id.name or '(No Employee)'
            rec.name = f"{tmpl} — {emp}"

    def _compute_score(self):
        """Compute score from auto-scoreable answers."""
        self.ensure_one()
        auto_types = ('multiple_choice', 'true_false')
        total_marks = sum(
            q.marks for q in self.template_id.question_ids
            if q.question_type in auto_types
        )
        if not total_marks:
            self.score = 0.0
            return
        earned = sum(
            a.question_id.marks
            for a in self.answer_ids
            if a.question_type in auto_types and a.is_correct
        )
        self.score = round((earned / total_marks) * 100, 2)

    def action_start(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('This assessment has already been started.'))
        # Create answer stubs if none exist
        if not self.answer_ids:
            answer_vals = []
            for question in self.template_id.question_ids:
                answer_vals.append({
                    'assessment_id': self.id,
                    'question_id': question.id,
                })
            if answer_vals:
                self.env['lms.assessment.answer'].create(answer_vals)
        self.write({
            'state': 'in_progress',
            'start_date': fields.Datetime.now(),
        })

    def action_submit(self):
        self.ensure_one()
        if self.state != 'in_progress':
            raise UserError(_('Only in-progress assessments can be submitted.'))
        # Recompute score
        self._compute_score()
        passing_score = self.template_id.passing_score

        # Check for short-text answers requiring manual review
        has_short_text = any(
            a.question_type == 'short_text' for a in self.answer_ids
        )
        if has_short_text:
            self.write({'state': 'submitted', 'submit_date': fields.Datetime.now()})
            return

        if self.delivery_type == 'electronic':
            if self.score >= passing_score:
                self.write({
                    'state': 'passed',
                    'passed': True,
                    'submit_date': fields.Datetime.now(),
                })
                self._notify_employee_record(True)
            else:
                self.write({
                    'state': 'failed',
                    'passed': False,
                    'submit_date': fields.Datetime.now(),
                })
                self._notify_employee_record(False)
        elif self.delivery_type == 'assessor_checklist':
            all_checked = all(
                a.is_checked for a in self.answer_ids
                if a.question_type == 'checklist_item'
            )
            if all_checked:
                self.write({
                    'state': 'passed',
                    'passed': True,
                    'submit_date': fields.Datetime.now(),
                })
                self._notify_employee_record(True)
            else:
                self.write({
                    'state': 'submitted',
                    'submit_date': fields.Datetime.now(),
                })

    def action_pass(self):
        self.ensure_one()
        self.write({'state': 'passed', 'passed': True})
        self._notify_employee_record(True)

    def action_fail(self):
        self.ensure_one()
        self.write({'state': 'failed', 'passed': False})
        self._notify_employee_record(False)

    def action_reset(self):
        self.ensure_one()
        self.answer_ids.unlink()
        self.write({
            'state': 'draft',
            'passed': False,
            'score': 0.0,
            'start_date': False,
            'submit_date': False,
        })

    def _notify_employee_record(self, passed):
        """Post a chatter message on the linked employee record."""
        self.ensure_one()
        if not self.employee_record_id:
            return
        result_str = _('Passed') if passed else _('Failed')
        body = _('Assessment <strong>%s</strong> completed — result: <strong>%s</strong> (score: %.2f%%)') % (
            self.name, result_str, self.score
        )
        self.employee_record_id.message_post(body=body)


class LmsAssessmentAnswer(models.Model):
    _name = 'lms.assessment.answer'
    _description = 'LMS Assessment Answer'
    _order = 'assessment_id, sequence, id'

    assessment_id = fields.Many2one(
        'lms.assessment', string='Assessment', required=True, ondelete='cascade'
    )
    question_id = fields.Many2one(
        'lms.assessment.question', string='Question', required=True, ondelete='cascade'
    )
    sequence = fields.Integer(
        related='question_id.sequence', store=True, string='Sequence'
    )
    question_text = fields.Text(
        related='question_id.question_text', readonly=True, string='Question'
    )
    question_type = fields.Selection(
        related='question_id.question_type', readonly=True, string='Type'
    )
    selected_option_id = fields.Many2one(
        'lms.assessment.question.option', string='Selected Option',
        domain="[('question_id', '=', question_id)]"
    )
    bool_answer = fields.Selection(
        [('true', 'True'), ('false', 'False')], string='Answer'
    )
    text_answer = fields.Text(string='Text Answer')
    is_checked = fields.Boolean(string='Checked')
    is_correct = fields.Boolean(
        string='Correct', compute='_compute_is_correct', store=True
    )

    @api.depends(
        'question_type',
        'selected_option_id',
        'question_id.correct_option_id',
        'bool_answer',
        'question_id.correct_bool',
    )
    def _compute_is_correct(self):
        for rec in self:
            q_type = rec.question_type
            if q_type == 'multiple_choice':
                if rec.selected_option_id and rec.question_id.correct_option_id:
                    rec.is_correct = (
                        rec.selected_option_id == rec.question_id.correct_option_id
                    )
                else:
                    rec.is_correct = False
            elif q_type == 'true_false':
                if rec.bool_answer:
                    rec.is_correct = (
                        (rec.bool_answer == 'true') == rec.question_id.correct_bool
                    )
                else:
                    rec.is_correct = False
            else:
                rec.is_correct = False

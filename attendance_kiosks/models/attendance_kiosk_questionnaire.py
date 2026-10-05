from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AttendanceKioskQuestionnaire(models.Model):
    _name = 'attendance.kiosk.questionnaire'
    _description = 'Attendance Kiosk Questionnaire'
    _inherit = ['mail.thread']
    _order = 'sequence, name'

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', help='Leave empty to use this questionnaire in every company.',
    )
    introduction = fields.Text(help='Shown above the questions on the kiosk.')
    blocked_message = fields.Text(
        string='Message When Refused',
        default=lambda self: _('Based on your answers you cannot sign in. Please speak to your supervisor.'),
        help='Shown when an answer refuses the sign in.',
    )
    question_ids = fields.One2many('attendance.kiosk.question', 'questionnaire_id', string='Questions', copy=True)
    question_count = fields.Integer(compute='_compute_question_count')

    @api.depends('question_ids')
    def _compute_question_count(self):
        for questionnaire in self:
            questionnaire.question_count = len(questionnaire.question_ids)

    def _kiosk_payload(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'introduction': self.introduction or '',
            'blocked_message': self.blocked_message or '',
            'questions': [{
                'id': question.id,
                'name': question.name,
                'help': question.help_text or '',
                'type': question.question_type,
                'required': question.required,
                'blocking_answer': question.blocking_answer,
                'options': [{
                    'id': option.id,
                    'name': option.name,
                    'blocks': option.blocks_sign_in,
                } for option in question.option_ids],
            } for question in self.question_ids],
        }


class AttendanceKioskQuestion(models.Model):
    _name = 'attendance.kiosk.question'
    _description = 'Attendance Kiosk Question'
    _order = 'questionnaire_id, sequence, id'

    questionnaire_id = fields.Many2one(
        'attendance.kiosk.questionnaire', required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Question', required=True, translate=True)
    help_text = fields.Char(string='Help', translate=True)
    question_type = fields.Selection(
        [('yes_no', 'Yes / No'),
         ('choice', 'Multiple Choice'),
         ('text', 'Text'),
         ('number', 'Number')],
        string='Answer Type', default='yes_no', required=True,
    )
    required = fields.Boolean(default=True)
    blocking_answer = fields.Selection(
        [('none', 'None'), ('yes', 'Yes'), ('no', 'No')],
        string='Refuse Sign In When', default='none', required=True,
        help='Refuse the sign in when the worker gives this answer.',
    )
    option_ids = fields.One2many('attendance.kiosk.question.option', 'question_id', string='Choices', copy=True)

    @api.constrains('question_type', 'option_ids')
    def _check_options(self):
        for question in self:
            if question.question_type == 'choice' and not question.option_ids:
                raise ValidationError(_('The multiple choice question "%s" needs at least one choice.', question.name))


class AttendanceKioskQuestionOption(models.Model):
    _name = 'attendance.kiosk.question.option'
    _description = 'Attendance Kiosk Question Choice'
    _order = 'question_id, sequence, id'

    question_id = fields.Many2one('attendance.kiosk.question', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Choice', required=True, translate=True)
    blocks_sign_in = fields.Boolean(string='Refuses Sign In')


class AttendanceKioskQuestionnaireLine(models.Model):
    _name = 'attendance.kiosk.questionnaire.line'
    _description = 'Attendance Kiosk Questionnaire Trigger'
    _order = 'kiosk_id, sequence, id'

    kiosk_id = fields.Many2one('attendance.kiosk', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='kiosk_id.company_id', store=True)
    sequence = fields.Integer(default=10)
    questionnaire_id = fields.Many2one(
        'attendance.kiosk.questionnaire', required=True, ondelete='restrict',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    trigger = fields.Selection(
        [('always', 'Every sign in'),
         ('first_of_day', 'First sign in of the day'),
         ('first_of_day_location', 'First sign in of the day at this location'),
         ('first_at_location', 'First ever sign in at this location')],
        string='Show On', default='always', required=True,
        help='Every sign in: every time the worker signs in at this kiosk.\n'
             'First sign in of the day: only when the worker has not signed in anywhere yet today.\n'
             'First sign in of the day at this location: only when the worker has not signed in '
             "at this kiosk's work location yet today.\n"
             "First ever sign in at this location: only the first time the worker signs in at this "
             "kiosk's work location.",
    )
    employee_domain = fields.Char(
        string='Ask', default='[]',
        help='Only ask employees matching this filter. Leave empty to ask everyone.',
    )

    @api.constrains('employee_domain')
    def _check_employee_domain(self):
        for line in self:
            line.kiosk_id._kiosk_validate_domain(line.employee_domain)

    def _is_due(self, history, today):
        """Whether this trigger fires for an employee.

        :param history: ``{'any': 'YYYY-MM-DD' or None, 'loc': 'YYYY-MM-DD' or None}``,
            the employee's last sign in anywhere / at this location
        :param today: today's date at the kiosk, 'YYYY-MM-DD'
        """
        self.ensure_one()
        if self.trigger == 'always':
            return True
        if self.trigger == 'first_of_day':
            return not history['any'] or history['any'] < today
        if self.trigger == 'first_of_day_location':
            return not history['loc'] or history['loc'] < today
        if self.trigger == 'first_at_location':
            return not history['loc']
        return False

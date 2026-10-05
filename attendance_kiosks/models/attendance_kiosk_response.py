from odoo import _, api, fields, models


class AttendanceKioskResponse(models.Model):
    _name = 'attendance.kiosk.response'
    _description = 'Attendance Kiosk Questionnaire Response'
    _order = 'date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    date = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True)
    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True, readonly=True)
    kiosk_id = fields.Many2one('attendance.kiosk', required=True, ondelete='cascade', index=True, readonly=True)
    company_id = fields.Many2one(related='kiosk_id.company_id', store=True)
    work_location_id = fields.Many2one(related='kiosk_id.work_location_id', store=True)
    questionnaire_id = fields.Many2one(
        'attendance.kiosk.questionnaire', required=True, ondelete='restrict', readonly=True,
    )
    attendance_id = fields.Many2one('hr.attendance', ondelete='set null', index=True, readonly=True)
    blocked = fields.Boolean(
        string='Sign In Refused', readonly=True,
        help='An answer in this response stopped the worker signing in.',
    )
    offline = fields.Boolean(string='Recorded Offline', readonly=True)
    line_ids = fields.One2many('attendance.kiosk.response.line', 'response_id', string='Answers', readonly=True)

    @api.depends('employee_id.name', 'questionnaire_id.name')
    def _compute_name(self):
        for response in self:
            response.name = f'{response.questionnaire_id.name or ""} - {response.employee_id.name or ""}'

    @api.model
    def _kiosk_prepare(self, kiosk, employee, questionnaires, answers, when, strict=True):
        """Turn the answers posted by the kiosk into response values.

        :param questionnaires: the questionnaires that must be recorded
        :param answers: ``[{'questionnaire_id': int, 'answers': {question_id: {'value': str,
            'option_id': int}}}]``
        :param strict: refuse when a required question is unanswered
        :return: ``(vals_list, blocked_messages, unanswered_questionnaires)``
        """
        given = {}
        for entry in answers or []:
            try:
                given[int(entry.get('questionnaire_id'))] = {
                    int(key): value or {} for key, value in (entry.get('answers') or {}).items()
                }
            except (TypeError, ValueError, AttributeError):
                continue

        vals_list, blocked, missing = [], [], questionnaires.browse()
        for questionnaire in questionnaires.sudo():
            questionnaire_answers = given.get(questionnaire.id)
            if questionnaire_answers is None:
                if strict:
                    missing |= questionnaire
                continue
            lines, refuses = [], False
            for question in questionnaire.question_ids:
                answer = questionnaire_answers.get(question.id) or {}
                if not isinstance(answer, dict):
                    answer = {'value': answer}
                value = str(answer.get('value') or '').strip()
                option = question.option_ids.filtered(lambda o, a=answer: o.id == a.get('option_id'))[:1]
                line_blocks = False
                if question.question_type == 'yes_no':
                    value = value if value in ('yes', 'no') else ''
                    line_blocks = bool(value) and question.blocking_answer == value
                    display = {'yes': _('Yes'), 'no': _('No')}.get(value, '')
                elif question.question_type == 'choice':
                    line_blocks = option.blocks_sign_in
                    display = option.name or ''
                    value = str(option.id) if option else ''
                elif question.question_type == 'number':
                    try:
                        value = str(float(value)) if value else ''
                    except ValueError:
                        value = ''
                    display = value
                else:
                    display = value
                if strict and question.required and not value:
                    missing |= questionnaire
                refuses = refuses or line_blocks
                lines.append(fields.Command.create({
                    'question_id': question.id,
                    'question': question.name,
                    'answer': display,
                    'option_id': option.id if question.question_type == 'choice' else False,
                    'blocks_sign_in': line_blocks,
                }))
            if refuses:
                blocked.append(questionnaire.blocked_message or _('Based on your answers you cannot sign in.'))
            vals_list.append({
                'date': when,
                'employee_id': employee.id,
                'kiosk_id': kiosk.id,
                'questionnaire_id': questionnaire.id,
                'offline': not strict,
                'line_ids': lines,
            })
        return vals_list, blocked, missing


class AttendanceKioskResponseLine(models.Model):
    _name = 'attendance.kiosk.response.line'
    _description = 'Attendance Kiosk Questionnaire Answer'
    _order = 'response_id, id'

    response_id = fields.Many2one('attendance.kiosk.response', required=True, ondelete='cascade', index=True)
    question_id = fields.Many2one('attendance.kiosk.question', string='Question Record', ondelete='set null')
    question = fields.Char(required=True, help='The question as it was asked.')
    answer = fields.Char()
    option_id = fields.Many2one('attendance.kiosk.question.option', ondelete='set null')
    blocks_sign_in = fields.Boolean(string='Refused Sign In')

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class RiskAssessment(models.Model):
    _name = 'risk.assessment'
    _description = 'Risk Assessment'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'risk.ai.mixin', 'risk.activity.mixin']
    _order = 'date desc, id desc'

    _ai_line_model = 'risk.assessment.line'
    _ai_line_parent_field = 'assessment_id'

    name = fields.Char(required=True, tracking=True)
    date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    review_due = fields.Date(
        string='Review Due', tracking=True,
        default=lambda self: fields.Date.context_today(self) + relativedelta(years=1),
        help='Defaults to one year after the assessment Date.',
    )
    assessor_id = fields.Many2one(
        'res.users', string='Risk Assessment Owner', default=lambda self: self.env.user, tracking=True,
    )
    approver_id = fields.Many2one(
        'res.users', string='Risk Approver', tracking=True,
        default=lambda self: self.env.user.team_leader_id,
        help="Defaults to the Risk Assessment Owner's Team Leader.",
    )
    collaborator_ids = fields.Many2many(
        'res.users', string='Collaborators',
        help='Additional users who can access this Risk Assessment even though they did not create it.',
    )
    stage_id = fields.Many2one(
        'risk.assessment.stage', string='Stage', tracking=True,
        default=lambda self: self.env['risk.assessment.stage'].search([('stage_type', '=', 'draft')], limit=1),
        copy=False,
    )
    stage_type = fields.Selection(related='stage_id.stage_type', string='Stage Type', store=True, readonly=True)
    can_approve = fields.Boolean(compute='_compute_can_approve')
    description = fields.Text()
    active = fields.Boolean(default=True)
    category_id = fields.Many2one('risk.category', string='Risk Category')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)

    template_ids = fields.Many2many('risk.template', string='Risk Assessment Templates')
    line_ids = fields.One2many('risk.assessment.line', 'assessment_id', string='Risks', copy=True)
    risk_count = fields.Integer(compute='_compute_risk_summary')
    highest_severity_id = fields.Many2one(
        'risk.severity', compute='_compute_risk_summary',
        help='Highest Residual Risk severity across this assessment\'s risks.',
    )
    todo_count = fields.Integer(compute='_compute_todo_summary')
    todo_open_count = fields.Integer(compute='_compute_todo_summary')

    @api.depends('line_ids.residual_severity_id', 'line_ids.residual_score')
    def _compute_risk_summary(self):
        for assessment in self:
            lines = assessment.line_ids
            assessment.risk_count = len(lines)
            top_line = lines.sorted(key=lambda line: line.residual_score or 0, reverse=True)[:1]
            assessment.highest_severity_id = top_line.residual_severity_id if top_line else False

    @api.depends('line_ids.todo_ids', 'line_ids.todo_ids.state')
    def _compute_todo_summary(self):
        for assessment in self:
            todos = assessment.line_ids.todo_ids
            assessment.todo_count = len(todos)
            assessment.todo_open_count = len(
                todos.filtered(lambda todo: todo.state not in ('1_done', '1_canceled'))
            )

    def _compute_can_approve(self):
        for assessment in self:
            user = self.env.user
            assessment.can_approve = bool(
                (assessment.approver_id and assessment.approver_id == user)
                or user.has_group('risk_management.group_risk_assessment_delete')
            )

    @api.onchange('assessor_id')
    def _onchange_assessor_id(self):
        if self.assessor_id:
            self.approver_id = self.assessor_id.team_leader_id

    @api.onchange('date')
    def _onchange_date_review_due(self):
        if self.date:
            self.review_due = self.date + relativedelta(years=1)

    @api.onchange('template_ids')
    def _onchange_template_ids(self):
        skipped = self._sync_template_lines()
        if skipped:
            return {'warning': {
                'title': 'Some risks were skipped',
                'message': self._skipped_template_lines_message(skipped),
            }}

    def action_load_template_risks(self):
        skipped = self._sync_template_lines()
        if skipped:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Some risks were skipped',
                    'message': self._skipped_template_lines_message(skipped),
                    'type': 'warning',
                    'sticky': True,
                },
            }

    def _skipped_template_lines_message(self, skipped):
        return (
            'These risks have no "Risk" text set on their template, so they were not copied '
            "in. Open the template and either give them a name or remove them, then use "
            '"Load Risks from Templates" again:\n- ' + '\n- '.join(skipped)
        )

    def _sync_template_lines(self):
        skipped = []
        for assessment in self:
            existing_source_ids = set(assessment.line_ids.mapped('source_template_line_id').ids)
            template_lines = assessment.template_ids.line_ids.filtered(
                lambda line: line.id not in existing_source_ids
            )
            blank_lines = template_lines.filtered(lambda line: not (line.name or '').strip())
            if blank_lines:
                skipped += [
                    'Template "%s": Risk #%s' % (line.template_id.name, line.id)
                    for line in blank_lines
                ]
                template_lines -= blank_lines
            new_lines = []
            for line in template_lines:
                new_lines.append((0, 0, {
                    'sequence': line.sequence,
                    'name': line.name,
                    'unwanted_event': line.unwanted_event,
                    'description': line.description,
                    'risk_type_id': line.risk_type_id.id,
                    'risk_subtype_id': line.risk_subtype_id.id,
                    'inherent_likelihood_id': line.inherent_likelihood_id.id,
                    'inherent_consequence_id': line.inherent_consequence_id.id,
                    'residual_likelihood_id': line.residual_likelihood_id.id,
                    'residual_consequence_id': line.residual_consequence_id.id,
                    'control_ids': [(6, 0, line.control_ids.ids)],
                    'control_summary': line.control_summary,
                    'source_template_line_id': line.id,
                }))
                existing_source_ids.add(line.id)
            if new_lines:
                assessment.line_ids = new_lines
        return skipped

    def _check_can_approve(self):
        self.ensure_one()
        if not self.can_approve:
            raise AccessError(
                'Only the assigned Risk Approver (or a user with Risk Assessments / Delete) can '
                'approve or reject this Risk Assessment.'
            )

    def _get_stage(self, stage_type):
        return self.env['risk.assessment.stage'].search([('stage_type', '=', stage_type)], limit=1)

    def action_set_in_progress(self):
        self.stage_id = self._get_stage('in_progress')

    def action_submit_for_approval(self):
        for assessment in self:
            if not assessment.approver_id:
                raise UserError('Set a Risk Approver before submitting this assessment for approval.')
        self.stage_id = self._get_stage('submitted')

    def action_open_approval_wizard(self):
        self.ensure_one()
        self._check_can_approve()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Review Risk Assessment',
            'res_model': 'risk.assessment.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_assessment_id': self.id},
        }

    def action_set_done(self):
        for assessment in self:
            if assessment.stage_type != 'approved':
                raise UserError('A Risk Assessment must be Approved before it can be marked Completed.')
        self.stage_id = self._get_stage('done')

    def action_set_draft(self):
        self.stage_id = self._get_stage('draft')

    def action_open_todos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Actions',
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.line_ids.todo_ids.ids)],
        }

    def action_export_pdf(self):
        self.ensure_one()
        return self.env.ref('risk_management.action_report_risk_assessment').report_action(self)

    def write(self, vals):
        if set(vals.keys()) == {'active'} and not self.env.user.has_group('risk_management.group_risk_assessment_delete'):
            raise AccessError(
                'Only a user with Risk Assessments / Delete can archive a Risk Assessment.'
            )
        return super().write(vals)

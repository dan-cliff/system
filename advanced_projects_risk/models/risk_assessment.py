from datetime import datetime, time

from odoo import _, fields, models


class RiskAssessment(models.Model):
    _inherit = 'risk.assessment'

    advanced_project_id = fields.Many2one(
        'advanced.project', string='Project', tracking=True, index='btree_not_null', ondelete='set null',
        domain=[('is_template', '=', False)])


class AdvancedProject(models.Model):
    _inherit = 'advanced.project'

    risk_assessment_ids = fields.One2many('risk.assessment', 'advanced_project_id', string='Risk Assessments')
    risk_assessment_count = fields.Integer('Risk Assessment Count', compute='_compute_risk_assessment_count')

    def _compute_risk_assessment_count(self):
        Assessment = self.env['risk.assessment']
        counts = {}
        if Assessment.has_access('read'):
            counts = dict(Assessment._read_group([('advanced_project_id', 'in', self.ids)],
                                                 ['advanced_project_id'], ['__count']))
        for project in self:
            project.risk_assessment_count = counts.get(project, 0)

    def _risk_assessment_values(self):
        """Values a new Risk Assessment for this project starts with."""
        self.ensure_one()
        colleagues = self.collaborator_ids.filtered(lambda c: c.collaborator_type == 'colleague').user_id
        start = datetime.combine(self.date_start or fields.Date.context_today(self), time(9, 0))
        return {
            'advanced_project_id': self.id,
            'name': _('%s – Risk Assessment', self.name),
            'activity_start': start,
            'company_id': self.company_id.id,
            'collaborator_ids': [(6, 0, colleagues.filtered(lambda u: not u.share).ids)],
            'description': _('Risk assessment for the project "%s".', self.name),
        }

    def action_new_risk_assessment(self):
        self.ensure_one()
        assessment = self.env['risk.assessment'].create(self._risk_assessment_values())
        return {
            'type': 'ir.actions.act_window',
            'name': assessment.name,
            'res_model': 'risk.assessment',
            'res_id': assessment.id,
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_open_risk_assessments(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('risk_management.action_risk_assessment')
        action.update({
            'name': _('%s – Risk Assessments', self.name),
            'domain': [('advanced_project_id', '=', self.id)],
            'context': {'default_advanced_project_id': self.id},
        })
        return action

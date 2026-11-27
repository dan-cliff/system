# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrJob(models.Model):
    _inherit = 'hr.job'

    talent_checklist_ids = fields.One2many(
        'checklist.checklist', 'talent_job_id', string='Questionnaires',
        groups='modern_recruitment_checklists.group_talent_questionnaire',
    )
    talent_checklist_count = fields.Integer(
        compute='_compute_talent_checklist_count',
        groups='modern_recruitment_checklists.group_talent_questionnaire',
    )

    @api.depends('talent_checklist_ids.state')
    def _compute_talent_checklist_count(self):
        counts = dict(self.env['checklist.checklist']._read_group(
            [('talent_job_id', 'in', self.ids), ('state', '=', 'done')], ['talent_job_id'], ['__count']))
        for job in self:
            job.talent_checklist_count = counts.get(job, 0)

    def action_talent_questionnaires(self):
        self.ensure_one()
        return self.env['hr.applicant']._talent_checklist_action(
            [('talent_job_id', '=', self.id)], self.env._('Questionnaires: %s', self.name))

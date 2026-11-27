# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    talent_checklist_enabled = fields.Boolean(string='Integrate Checklists with Talent')
    talent_checklist_group_ids = fields.Many2many(
        'checklist.group', 'res_company_talent_checklist_group_rel', 'company_id', 'group_id',
        string='Talent Checklist Groups',
        help='Talent can send the templates in these Checklist Groups to applicants.',
    )

    def _talent_questionnaire_templates(self):
        """The checklist templates Talent may send (none unless integrated)."""
        self.ensure_one()
        if not self.talent_checklist_enabled or not self.talent_checklist_group_ids:
            return self.env['checklist.template']
        return self.env['checklist.template'].sudo().search(
            [('group_ids', 'in', self.talent_checklist_group_ids.ids)]).sudo(False)

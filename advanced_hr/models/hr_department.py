# -*- coding: utf-8 -*-
from odoo import fields, models


class HrDepartment(models.Model):
    _name = 'hr.department'
    _inherit = ['advanced.hr.audit.mixin', 'hr.department']

    personnel_audit_count = fields.Integer(
        string='Audit Trail', compute='_compute_personnel_audit_count',
        groups='advanced_hr.group_audit_trail_view')

    def _compute_personnel_audit_count(self):
        counts = dict(self.env['advanced.hr.audit.trail']._read_group(
            [('res_model', '=', 'hr.department'), ('res_id', 'in', self.ids)],
            ['res_id'], ['__count'],
        )) if self.ids else {}
        for department in self:
            department.personnel_audit_count = counts.get(department.id, 0)

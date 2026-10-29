# -*- coding: utf-8 -*-
from odoo import fields, models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    # The ID badge this print action draws (one action per badge).
    badge_template_id = fields.Many2one(
        'advanced.hr.badge.template', string='ID Badge', ondelete='cascade', index='btree_not_null')

    def _get_rendering_context(self, report, docids, data):
        if report.badge_template_id:
            data = dict(data or {}, badge_template_id=report.badge_template_id.id)
        return super()._get_rendering_context(report, docids, data)

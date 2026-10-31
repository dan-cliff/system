# -*- coding: utf-8 -*-
from odoo import fields, models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    # The label design this print action draws (one action per label design).
    inventory_label_template_id = fields.Many2one(
        'advanced.inventory.label.template', string='Label Design', ondelete='cascade', index='btree_not_null')

    def _get_rendering_context(self, report, docids, data):
        if report.inventory_label_template_id:
            data = dict(data or {}, inventory_label_template_id=report.inventory_label_template_id.id)
        return super()._get_rendering_context(report, docids, data)

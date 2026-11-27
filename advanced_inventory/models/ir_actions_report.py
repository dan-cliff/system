# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

LABEL_REPORT_PREFIX = 'advanced_inventory.report_label_'


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    # The label design this print action draws (one action per label design).
    inventory_label_template_id = fields.Many2one(
        'advanced.inventory.label.template', string='Label Design', ondelete='cascade', index='btree_not_null')

    def _get_rendering_context_model(self, report):
        if report.inventory_label_template_id:
            return self.env['report.advanced_inventory.report_label']
        return super()._get_rendering_context_model(report)

    def _render_template(self, template, values=None):
        if isinstance(template, str) and template.startswith(LABEL_REPORT_PREFIX):
            template = 'advanced_inventory.report_label'
        return super()._render_template(template, values)

    def _get_rendering_context(self, report, docids, data):
        if report.inventory_label_template_id:
            data = dict(data or {}, inventory_label_template_id=report.inventory_label_template_id.id,
                        inventory_label_model=report.model)
        return super()._get_rendering_context(report, docids, data)

    @api.model
    def _get_report(self, report_ref):
        if isinstance(report_ref, str) and report_ref.startswith(LABEL_REPORT_PREFIX) and not self.env[
                'ir.actions.report'].sudo().search_count([('report_name', '=', report_ref)], limit=1):
            # A label design deleted while a page still offered it in its Print menu.
            raise UserError(self.env._(
                'This label design has been deleted, so its labels can\'t be printed. Reload the page '
                'to refresh the Print menu, then pick another label, or add a design in '
                'Inventory › Configuration › Labels & Signage › Label Designs.'))
        return super()._get_report(report_ref)

    def get_valid_action_reports(self, model, record_ids):
        # The web client keeps a cached copy of each view's Print menu, so it can still
        # offer the print action of a label design that has just been deleted: leave
        # those out instead of failing with "Record does not exist or has been deleted".
        return super(IrActionsReport, self.exists()).get_valid_action_reports(model, record_ids)

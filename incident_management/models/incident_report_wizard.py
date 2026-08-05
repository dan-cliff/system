# -*- coding: utf-8 -*-
from odoo import api, fields, models


class IncidentReportWizard(models.TransientModel):
    """Wizard to build a selective PDF export of an Incident Report."""

    _name = 'incident.report.wizard'
    _description = 'Incident Report PDF Export Wizard'

    incident_id = fields.Many2one(
        'incident.report', string='Incident Report',
        required=True, ondelete='cascade')

    include_report = fields.Boolean('Report Details', default=True)
    include_investigation = fields.Boolean('Investigation', default=True)
    include_corrective_actions = fields.Boolean('Corrective Actions', default=True)

    # Guidance counts
    category_count = fields.Integer(compute='_compute_counts')
    finding_count = fields.Integer(compute='_compute_counts')
    corrective_action_count = fields.Integer(compute='_compute_counts')

    @api.depends('incident_id')
    def _compute_counts(self):
        for w in self:
            w.category_count = len(w.incident_id.incident_type_ids)
            w.finding_count = w.incident_id.finding_count
            w.corrective_action_count = w.incident_id.corrective_action_count

    def action_print(self):
        self.ensure_one()
        return (
            self.env.ref('incident_management.action_report_incident_full')
            .report_action(self)
        )

# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ReportBuilderColumn(models.Model):
    _name = 'report.builder.column'
    _description = 'Report Builder Column'
    _order = 'report_id, sequence, id'

    report_id = fields.Many2one(
        'report.builder', string='Report', required=True, ondelete='cascade'
    )
    sequence = fields.Integer(string='Sequence', default=10)

    # Inherited from parent — tells the field_selector widget which model to browse
    model_name = fields.Char(
        related='report_id.model_name',
        string='Model Name',
        store=False,
    )

    # Field selection
    field_path = fields.Char(
        string='Field Path', required=True,
        help='Dot-notation field path, e.g. "partner_id.country_id.name". '
             'Use the field selector to build this path.'
    )
    label = fields.Char(
        string='Column Header',
        help='Custom label for the column header. Defaults to the field name if empty.'
    )

    # Display
    width = fields.Integer(
        string='Width (chars)', default=0,
        help='Suggested column width in characters. 0 = auto.'
    )

    # Computed display
    display_name_field = fields.Char(
        string='Display', compute='_compute_display_name_field', store=False
    )

    @api.depends('field_path', 'label')
    def _compute_display_name_field(self):
        for rec in self:
            rec.display_name_field = rec.label or rec.field_path or ''

    @api.onchange('field_path')
    def _onchange_field_path(self):
        """Auto-populate label from the last segment of the field path."""
        if self.field_path and not self.label:
            last_part = self.field_path.split('.')[-1]
            # Try to look up the field description
            if self.report_id and self.report_id.model_name:
                try:
                    model = self.env[self.report_id.model_name]
                    # Walk the path to get the final field
                    parts = self.field_path.split('.')
                    current_model = model
                    for i, part in enumerate(parts):
                        if hasattr(current_model, '_fields') and part in current_model._fields:
                            field_obj = current_model._fields[part]
                            if i == len(parts) - 1:
                                self.label = field_obj.string or last_part
                            elif hasattr(field_obj, 'comodel_name') and field_obj.comodel_name:
                                current_model = self.env[field_obj.comodel_name]
                        else:
                            break
                except Exception:
                    self.label = last_part.replace('_', ' ').title()
            else:
                self.label = last_part.replace('_', ' ').title()

# -*- coding: utf-8 -*-
from odoo import fields, models


class EsmInspectionLineMixin(models.AbstractModel):
    """Shared behaviour of inspection checks (answer lines)."""
    _name = 'esm.inspection.line.mixin'
    _description = 'ESM Inspection Check'

    def _answer_display(self):
        """The answer as text, for reports (dates as dd/mm/yyyy)."""
        self.ensure_one()
        kind = self.question_type
        if kind == 'text':
            return self.value_text or ''
        if kind == 'text_area':
            return self.value_text_area or ''
        if kind == 'number':
            return ('%.2f' % self.value_number).rstrip('0').rstrip('.')
        if kind == 'integer':
            return str(self.value_integer)
        if kind == 'date':
            return self.value_date.strftime('%d/%m/%Y') if self.value_date else ''
        if kind == 'datetime':
            if not self.value_datetime:
                return ''
            return fields.Datetime.context_timestamp(self, self.value_datetime).strftime('%d/%m/%Y %H:%M')
        if kind == 'buttons':
            return self.value_option_id.name or ''
        return ''

    def _answer_badge_style(self):
        """Inline style colouring a Buttons answer like its button, or ''."""
        self.ensure_one()
        colour = self.question_type == 'buttons' and self.value_option_id.color
        if not colour:
            return ''
        hex_colour = colour.lstrip('#')
        try:
            r, g, b = (int(hex_colour[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return ''
        text = '#000' if 0.299 * r + 0.587 * g + 0.114 * b > 160 else '#fff'
        return f'background-color: {colour}; color: {text};'

from datetime import timedelta

from odoo import _, api, fields, models


def format_hours(hours):
    """Hours as H:MM, like the timesheet grid."""
    minutes = round((hours or 0.0) * 60)
    return '%d:%02d' % divmod(minutes, 60)


class AdvancedProjectOverviewWidget(models.Model):
    _inherit = 'advanced.project.overview.widget'

    widget_type = fields.Selection(
        selection_add=[('hours_total', 'Project Working Hours Total'),
                       ('hours_by_person', 'Project Working Hours by Person')],
        ondelete={'hours_total': 'cascade', 'hours_by_person': 'cascade'})

    @api.model
    def _widget_palette_info(self):
        info = super()._widget_palette_info()
        info.update({
            'hours_total': ('fa-clock-o', 'Hours booked on timesheets to the project and its tasks.'),
            'hours_by_person': ('fa-user-circle', 'Hours booked to the project, per person.'),
        })
        return info

    def _project_hours_lines(self):
        # sudo: totals for everyone who can open the project (see advanced_project.py)
        return self.env['advanced.timesheet.line'].sudo().search([('advanced_project_id', '=', self.project_id.id)])

    def _data_hours_total(self):
        lines = self._project_hours_lines()
        total = sum(lines.mapped('unit_amount'))
        since = fields.Date.context_today(self) - timedelta(days=30)
        recent = sum(lines.filtered(lambda l: l.date >= since).mapped('unit_amount'))
        on_tasks = sum(lines.filtered('advanced_task_id').mapped('unit_amount'))
        people = len(lines.user_id)
        if not lines:
            caption = _('No hours booked yet.')
        elif people == 1:
            caption = _('booked by 1 person')
        else:
            caption = _('booked by %s people', people)
        return {
            'render': 'stat',
            'value': format_hours(total),
            'unit': _('hours'),
            'caption': caption,
            'details': [
                {'label': _('Last 30 days'), 'value': format_hours(recent)},
                {'label': _('On tasks'), 'value': format_hours(on_tasks)},
                {'label': _('On the project itself'), 'value': format_hours(total - on_tasks)},
            ],
        }

    def _data_hours_by_person(self):
        totals = {}
        for line in self._project_hours_lines():
            name = line.user_id.name or line.person_name or _('Unknown')
            totals[name] = totals.get(name, 0.0) + line.unit_amount
        top = max(totals.values() or [0.0]) or 1.0
        rows = [{'label': name, 'value': format_hours(hours), 'percent': round(100 * hours / top)}
                for name, hours in sorted(totals.items(), key=lambda item: -item[1])]
        return {'render': 'bars', 'rows': rows, 'empty': _('No hours booked yet.')}

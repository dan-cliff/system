from odoo import _, api, fields, models

from .advanced_project_options import CLOSED_CATEGORIES
from .advanced_project_task_filter import format_date

# The widgets the Overview can show. Each is drawn by its own code in the
# Overview client action, so the list stays a fixed selection
# (CLAUDE.md > Choice fields: technical states).
WIDGET_TYPES = [
    ('progress', 'Progress'),
    ('task_counts', 'Task Summary'),
    ('phases', 'Phase Progress'),
    ('task_list', 'Task List'),
    ('stage_chart', 'Tasks by Stage'),
    ('workload', 'Workload'),
    ('team', 'Team'),
    ('latest_update', 'Latest Update'),
    ('note', 'Note'),
]

WIDGET_PALETTE = {
    'progress': ('fa-tachometer', 'Tasks done and time elapsed between the start and target end dates.'),
    'task_counts': ('fa-th-large', 'Outstanding, upcoming, completed, blocked and overdue task counts.'),
    'phases': ('fa-list-ol', 'Each phase with its dates and progress.'),
    'task_list': ('fa-tasks', 'A filtered list of tasks: outstanding, upcoming, completed, blocked, ...'),
    'stage_chart': ('fa-bar-chart', 'How many tasks sit in each stage.'),
    'workload': ('fa-users', 'Open and overdue tasks per assignee.'),
    'team': ('fa-address-book', 'Colleagues and customers on the project.'),
    'latest_update': ('fa-bullhorn', 'The latest published Project Update.'),
    'note': ('fa-sticky-note', 'Free text, e.g. goals, links or key contacts.'),
}

# Column span in the Overview's 12-column grid, set per widget.
WIDTHS = [
    ('small', 'One Third'),
    ('medium', 'Half'),
    ('large', 'Two Thirds'),
    ('full', 'Full Width'),
]


class AdvancedProjectOverviewWidget(models.Model):
    _name = 'advanced.project.overview.widget'
    _description = 'Project Overview Widget'
    _inherit = ['advanced.project.task.filter.mixin']
    _order = 'sequence, id'

    project_id = fields.Many2one(
        'advanced.project', string='Project', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='project_id.company_id', store=True, index=True)
    sequence = fields.Integer(default=10)
    widget_type = fields.Selection(WIDGET_TYPES, string='Widget', required=True, default='task_list')
    name = fields.Char('Title', help='Leave empty to use the default title.')
    width = fields.Selection(WIDTHS, required=True, default='small')
    note = fields.Html()
    upcoming_days = fields.Integer(
        'Upcoming Within (days)', default=14, help='Task Summary: what counts as upcoming.')

    def _filter_project(self):
        return self.project_id

    def _default_title(self):
        self.ensure_one()
        if self.widget_type == 'task_list':
            labels = dict(self._fields['task_filter']._description_selection(self.env))
            return _('%s Tasks', labels.get(self.task_filter, ''))
        return dict(self._fields['widget_type']._description_selection(self.env)).get(self.widget_type, '')

    @api.model
    def _palette(self):
        labels = dict(self._fields['widget_type']._description_selection(self.env))
        filters = dict(self._fields['task_filter']._description_selection(self.env))
        palette = []
        for widget_type, __ in WIDGET_TYPES:
            icon, description = WIDGET_PALETTE[widget_type]
            palette.append({'type': widget_type, 'label': labels[widget_type], 'icon': icon,
                            'description': description, 'task_filter': False})
        # quick picks for the common task lists
        for task_filter in ('outstanding', 'upcoming', 'completed', 'blocked', 'overdue', 'milestones'):
            palette.append({'type': 'task_list', 'label': _('%s Tasks', filters[task_filter]),
                            'icon': 'fa-tasks', 'description': '', 'task_filter': task_filter})
        return palette

    def _copy_layout_values(self, project, phase_map):
        """Values to recreate this widget on ``project`` (templates, copies)."""
        self.ensure_one()
        return {
            'project_id': project.id,
            'sequence': self.sequence,
            'widget_type': self.widget_type,
            'name': self.name,
            'width': self.width,
            'note': self.note,
            'upcoming_days': self.upcoming_days,
            'task_filter': self.task_filter,
            'days': self.days,
            'phase_ids': [(6, 0, [phase_map[p.id].id for p in self.phase_ids if p.id in phase_map])],
            'user_ids': [(6, 0, self.user_ids.ids)],
            'task_limit': self.task_limit,
            'show_assignees': self.show_assignees,
            'show_dates': self.show_dates,
            'show_phase': self.show_phase,
            'show_stage': self.show_stage,
            'customer_visible_only': self.customer_visible_only,
        }

    def _overview_values(self):
        self.ensure_one()
        return {
            'id': self.id,
            'widget_type': self.widget_type,
            'title': self.name or self._default_title(),
            'width': self.width,
            'data': getattr(self, f'_data_{self.widget_type}')(),
        }

    def get_widget_values(self):
        """One widget again, after it was configured."""
        return [widget._overview_values() for widget in self]

    # ------------------------------------------------------------
    # Data per widget type
    # ------------------------------------------------------------

    def _tasks(self):
        return self.env['advanced.project.task'].search([('project_id', '=', self.project_id.id)])

    def _data_progress(self):
        project = self.project_id
        tasks = self._tasks().filtered(lambda t: t.stage_category != 'cancelled')
        done = tasks.filtered(lambda t: t.stage_category == 'done')
        today = fields.Date.context_today(self)
        time_progress = days_left = None
        if project.date_start and project.date_end and project.date_end >= project.date_start:
            total_days = (project.date_end - project.date_start).days or 1
            elapsed = (today - project.date_start).days
            time_progress = max(0, min(100, round(100 * elapsed / total_days)))
            days_left = (project.date_end - today).days
        return {
            'progress': round(100 * len(done) / len(tasks)) if tasks else 0,
            'done': len(done),
            'total': len(tasks),
            'date_start': format_date(project.date_start),
            'date_end': format_date(project.date_end),
            'time_progress': time_progress,
            'days_left': days_left,
        }

    def _data_task_counts(self):
        Task = self.env['advanced.project.task']
        project_domain = [('project_id', '=', self.project_id.id)]
        counts = []
        for task_filter, label, color in (
            ('outstanding', _('Outstanding'), '#0A6CF0'),
            ('upcoming', _('Upcoming'), '#8E5CF0'),
            ('completed', _('Completed'), '#14A3A3'),
            ('blocked', _('Blocked'), '#FF9F1C'),
            ('overdue', _('Overdue'), '#FF5A6E'),
        ):
            days = self.upcoming_days if task_filter == 'upcoming' else 0
            domain = project_domain + list(self._task_filter_domain_for(task_filter, days))
            counts.append({'filter': task_filter, 'label': label, 'color': color, 'days': days,
                           'count': Task.search_count(domain)})
        return {'counts': counts}

    def _data_phases(self):
        return {'phases': self.project_id.phase_ids._overview_values()}

    def _data_task_list(self):
        return self._filter_values()

    def _data_stage_chart(self):
        Task = self.env['advanced.project.task']
        counts = dict(Task._read_group([('project_id', '=', self.project_id.id)], ['stage_id'], ['__count']))
        stages = self.env['advanced.project.task.stage'].search([])
        rows = [{'id': stage.id, 'name': stage.name, 'color': stage.color or '#3BB8FF',
                 'count': counts.get(stage, 0)} for stage in stages]
        top = max([r['count'] for r in rows] or [0]) or 1
        for row in rows:
            row['percent'] = round(100 * row['count'] / top)
        return {'stages': rows}

    def _data_workload(self):
        today = fields.Date.context_today(self)
        tasks = self._tasks().filtered(lambda t: t.stage_category not in CLOSED_CATEGORIES)
        people = {}
        for task in tasks:
            overdue = bool(task.date_end and task.date_end < today)
            for user in task.user_ids or [False]:
                key = user.id if user else 0
                row = people.setdefault(key, {
                    'id': key, 'name': user.name if user else _('Unassigned'), 'open': 0, 'overdue': 0,
                })
                row['open'] += 1
                row['overdue'] += overdue
        rows = sorted(people.values(), key=lambda r: (r['id'] == 0, -r['open'], r['name']))
        top = max([r['open'] for r in rows] or [0]) or 1
        for row in rows:
            row['percent'] = round(100 * row['open'] / top)
        return {'people': rows}

    def _data_team(self):
        members = []
        for collaborator in self.project_id.collaborator_ids:
            members.append({
                'id': collaborator.id,
                'partner_id': collaborator.partner_id.id,
                'name': collaborator.partner_id.display_name,
                'email': collaborator.partner_id.email or '',
                'type': collaborator.collaborator_type,
                'access_state': collaborator.access_state,
                'is_manager': collaborator.partner_id == self.project_id.user_id.partner_id,
            })
        return {
            'colleagues': [m for m in members if m['type'] == 'colleague'],
            'customers': [m for m in members if m['type'] == 'customer'],
        }

    def _data_latest_update(self):
        update = self.env['advanced.project.update'].search(
            [('project_id', '=', self.project_id.id), ('state', '=', 'published')],
            order='date desc, id desc', limit=1)
        if not update:
            return {'update': False}
        return {'update': {
            'id': update.id,
            'name': update.name,
            'date': format_date(update.date),
            'author': update.user_id.name or '',
            'status': update.status_id.name or '',
            'status_color': update.status_id.color or '',
            'summary': update.summary or '',
        }}

    def _data_note(self):
        return {'note': self.note or ''}

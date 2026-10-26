from datetime import timedelta

from odoo import _, api, fields, models
from odoo.fields import Domain

from .advanced_project_options import CLOSED_CATEGORIES

# Which tasks a widget lists. The filters are built in code, so this stays a
# fixed selection (CLAUDE.md > Choice fields: technical states).
TASK_FILTERS = [
    ('outstanding', 'Outstanding'),
    ('upcoming', 'Upcoming'),
    ('completed', 'Completed'),
    ('blocked', 'Blocked'),
    ('overdue', 'Overdue'),
    ('milestones', 'Milestones'),
    ('all', 'All'),
]


def format_date(value):
    """Dates for the dashboards and updates, as dd/mm/yyyy (CLAUDE.md > Dates)."""
    return value.strftime('%d/%m/%Y') if value else ''


class AdvancedProjectTaskFilterMixin(models.AbstractModel):
    """A filtered list of a project's tasks, shared by the Overview's task
    widgets and the task widgets of Project Updates."""
    _name = 'advanced.project.task.filter.mixin'
    _description = 'Project Task Filter'

    task_filter = fields.Selection(
        TASK_FILTERS, string='Show', default='outstanding', required=True,
        help='Outstanding: not done or cancelled. Upcoming: starting or due within the next days. '
             'Completed: done (within the last days). Blocked: in a Blocked stage. Overdue: past '
             'their end date and not done. Milestones: tasks marked as milestones.')
    days = fields.Integer(
        'Within (days)', default=14,
        help='Upcoming: starting or due within this many days. Completed: done within the last '
             'this many days. 0 for any time.')
    phase_ids = fields.Many2many(
        'advanced.project.phase', string='Phases', help='Only tasks in these phases (all phases when empty).')
    user_ids = fields.Many2many(
        'res.users', string='Assignees', help='Only tasks assigned to these people (everyone when empty).')
    task_limit = fields.Integer('Show at Most', default=10, help='Number of tasks listed; 0 lists them all.')
    show_assignees = fields.Boolean('Show Assignees', default=True)
    show_dates = fields.Boolean('Show Dates', default=True)
    show_phase = fields.Boolean('Show Phase', default=True)
    show_stage = fields.Boolean('Show Stage', default=True)
    customer_visible_only = fields.Boolean(
        'Customer-Visible Tasks Only', help='Leave out tasks hidden from customers.')

    def _filter_project(self):
        """The project whose tasks are filtered."""
        raise NotImplementedError()

    @api.model
    def _task_filter_domain_for(self, task_filter, days):
        today = fields.Date.context_today(self)
        open_domain = Domain('stage_category', 'not in', CLOSED_CATEGORIES)
        if task_filter == 'outstanding':
            return open_domain
        if task_filter == 'upcoming':
            window = Domain('date_start', '>=', today) | Domain('date_end', '>=', today)
            if days:
                until = today + timedelta(days=days)
                window = ((Domain('date_start', '>=', today) & Domain('date_start', '<=', until))
                          | (Domain('date_end', '>=', today) & Domain('date_end', '<=', until)))
            return open_domain & window
        if task_filter == 'completed':
            domain = Domain('stage_category', '=', 'done')
            if days:
                domain &= Domain('date_done', '>=', fields.Datetime.now() - timedelta(days=days))
            return domain
        if task_filter == 'blocked':
            return Domain('stage_category', '=', 'blocked')
        if task_filter == 'overdue':
            return open_domain & Domain('date_end', '<', today)
        if task_filter == 'milestones':
            return Domain('is_milestone', '=', True)
        return Domain.TRUE

    def _task_domain(self):
        self.ensure_one()
        domain = (Domain('project_id', '=', self._filter_project().id)
                  & self._task_filter_domain_for(self.task_filter, self.days))
        if self.phase_ids:
            domain &= Domain('phase_id', 'in', self.phase_ids.ids)
        if self.user_ids:
            domain &= Domain('user_ids', 'in', self.user_ids.ids)
        if self.customer_visible_only:
            domain &= Domain('customer_visible', '=', True)
        return domain

    def _task_order(self):
        if self.task_filter == 'completed':
            return 'date_done desc, id desc'
        return 'date_end asc, date_start asc, sequence, id'

    def _get_tasks(self):
        self.ensure_one()
        Task = self.env['advanced.project.task']
        total = Task.search_count(self._task_domain())
        tasks = Task.search(self._task_domain(), order=self._task_order(), limit=self.task_limit or None)
        return tasks, total

    def _task_rows(self, tasks):
        today = fields.Date.context_today(self)
        return [{
            'id': task.id,
            'name': task.name,
            'phase': task.phase_id.name or '',
            'stage': task.stage_id.name or '',
            'stage_category': task.stage_category or 'todo',
            'stage_color': task.stage_id.color or '',
            'assignees': ', '.join(task.user_ids.mapped('name')),
            'date_start': format_date(task.date_start),
            'date_end': format_date(task.date_end),
            'date_done': format_date(task.date_done and task.date_done.date()),
            'overdue': bool(task.date_end and task.date_end < today
                            and task.stage_category not in CLOSED_CATEGORIES),
            'is_milestone': task.is_milestone,
        } for task in tasks]

    def _filter_summary(self):
        """A short description of the filter, e.g. "Upcoming · next 14 days · Discovery"."""
        self.ensure_one()
        labels = dict(self._fields['task_filter']._description_selection(self.env))
        parts = [labels.get(self.task_filter, '')]
        if self.days and self.task_filter == 'upcoming':
            parts.append(_('next %s days', self.days))
        elif self.days and self.task_filter == 'completed':
            parts.append(_('last %s days', self.days))
        if self.phase_ids:
            parts.append(', '.join(self.phase_ids.mapped('name')))
        if self.user_ids:
            parts.append(', '.join(self.user_ids.mapped('name')))
        if self.customer_visible_only:
            parts.append(_('customer-visible only'))
        return ' · '.join(p for p in parts if p)

    def _filter_values(self):
        """The filter's settings and tasks, for the Overview and the update editor."""
        self.ensure_one()
        tasks, total = self._get_tasks()
        return {
            'task_filter': self.task_filter,
            'days': self.days,
            'phase_ids': self.phase_ids.ids,
            'user_ids': self.user_ids.ids,
            'task_limit': self.task_limit,
            'show_assignees': self.show_assignees,
            'show_dates': self.show_dates,
            'show_phase': self.show_phase,
            'show_stage': self.show_stage,
            'customer_visible_only': self.customer_visible_only,
            'summary': self._filter_summary(),
            'rows': self._task_rows(tasks),
            'total': total,
        }

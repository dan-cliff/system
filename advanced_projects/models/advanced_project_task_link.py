from collections import deque
from datetime import timedelta

from odoo import _, api, fields, models

from .advanced_project_task_filter import format_date

# How a child task follows its parent. The Gantt chart draws and checks each
# kind differently, so it stays a fixed selection (CLAUDE.md > Choice fields:
# technical states).
LINK_TYPES = [
    ('finish_start', 'End to Start'),
    ('start_start', 'Start to Start'),
    ('finish_finish', 'End to End'),
    ('start_finish', 'Start to End'),
]
DEFAULT_LINK_TYPE = 'finish_start'


class AdvancedProjectTaskLink(models.Model):
    """The kind of a parent → child link between two tasks (the link itself is
    the tasks' Parent / Child Tasks): End to Start (the child starts when the
    parent ends), Start to Start, End to End or Start to End."""
    _name = 'advanced.project.task.link'
    _description = 'Project Task Link'
    _order = 'parent_id, id'
    _rec_name = 'child_id'

    parent_id = fields.Many2one(
        'advanced.project.task', string='Parent Task', required=True, index=True, ondelete='cascade')
    child_id = fields.Many2one(
        'advanced.project.task', string='Child Task', required=True, index=True, ondelete='cascade')
    link_type = fields.Selection(LINK_TYPES, string='Link', required=True, default=DEFAULT_LINK_TYPE)
    project_id = fields.Many2one(related='parent_id.project_id', store=True, index=True)
    company_id = fields.Many2one(related='parent_id.company_id', store=True, index=True)

    _pair_uniq = models.Constraint('unique (parent_id, child_id)', 'These tasks are already linked.')

    def _required_shift(self, parent_dates=None, child_dates=None):
        """Days the child must move later to follow its parent, by the link's
        kind (0 when it already does or a task has no dates):

        * End to Start: the child starts the day after the parent ends;
        * Start to Start: the child starts when the parent starts;
        * End to End: the child ends when the parent ends;
        * Start to End: the child ends when the parent starts.

        ``parent_dates`` / ``child_dates`` are (first day, last day) to use
        instead of the tasks' own dates (e.g. while planning a reschedule)."""
        self.ensure_one()
        p_first, p_last = parent_dates or self.parent_id._gantt_span()
        c_first, c_last = child_dates or self.child_id._gantt_span()
        if not (p_first and c_first):
            return 0
        required, actual = {
            'finish_start': (p_last + timedelta(days=1), c_first),
            'start_start': (p_first, c_first),
            'finish_finish': (p_last, c_last),
            'start_finish': (p_first, c_last),
        }[self.link_type]
        return max(0, (required - actual).days)

    def _gantt_reschedule_plan(self):
        """{task: (new first day, new last day)} moving this link's child later
        to follow its parent, then each task linked after a moved one as far
        as its own link needs. Nothing ever moves earlier."""
        self.ensure_one()
        shift = self._required_shift()
        if not shift:
            return {}
        Task = self.env['advanced.project.task']
        plan = {}

        def span(task):
            return plan.get(task) or task._gantt_span()

        def move(task, days):
            first, last = span(task)
            plan[task] = (first + timedelta(days=days), last + timedelta(days=days))

        move(self.child_id, shift)
        queue = deque([self.child_id])
        while queue:
            task = queue.popleft()
            # sudo: plan through every link, the writes are checked as the user
            for link in task.sudo().child_link_ids:
                child = Task.browse(link.child_id.id)
                days = link._required_shift(span(task), span(child))
                if days:
                    move(child, days)
                    queue.append(child)
        return plan

    def _gantt_reschedule_proposal(self):
        """What the Gantt chart asks before rescheduling, or False when the
        child already follows its parent."""
        self.ensure_one()
        plan = self._gantt_reschedule_plan()
        if not plan:
            return False
        parent, child = self.parent_id, self.child_id
        rules = {
            'finish_start': _('start the day after “%(parent)s” ends (%(date)s)'),
            'start_start': _('start when “%(parent)s” starts (%(date)s)'),
            'finish_finish': _('end when “%(parent)s” ends (%(date)s)'),
            'start_finish': _('end when “%(parent)s” starts (%(date)s)'),
        }
        p_first, p_last = parent._gantt_span()
        date = {
            'finish_start': p_last + timedelta(days=1) if p_last else False,
            'start_start': p_first,
            'finish_finish': p_last,
            'start_finish': p_first,
        }[self.link_type]

        def dates(first, last):
            return format_date(first) if first == last else f'{format_date(first)} – {format_date(last)}'

        moves = [{
            'id': task.id,
            'name': task.name,
            'from': dates(*task._gantt_span()),
            'to': dates(first, last),
        } for task, (first, last) in plan.items()]
        return {
            'parent_id': parent.id,
            'child_id': child.id,
            'link_type': self.link_type,
            'message': _(
                '“%(child)s” is scheduled before its parent “%(parent)s”. The %(type)s link needs it to '
                '%(rule)s.',
                child=child.name, parent=parent.name,
                type=dict(self._fields['link_type']._description_selection(self.env))[self.link_type],
                rule=rules[self.link_type] % {'parent': parent.name, 'date': format_date(date)},
            ),
            'moves': moves,
        }


class AdvancedProjectTask(models.Model):
    _inherit = 'advanced.project.task'

    child_link_ids = fields.One2many(
        'advanced.project.task.link', 'parent_id', string='Child Task Links',
        help='How each child task follows this one: End to Start, Start to Start, End to End or Start to End.')

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        linked = tasks.filtered(lambda t: t.parent_ids or t.child_ids)
        if linked:
            (linked | linked.parent_ids | linked.child_ids)._sync_links()
        return tasks

    def write(self, vals):
        link_fields = {'parent_ids', 'child_ids'} & set(vals)
        before = (self.parent_ids | self.child_ids) if link_fields else self.browse()
        res = super().write(vals)
        if link_fields:
            (self | before | self.parent_ids | self.child_ids)._sync_links()
        return res

    def _sync_links(self):
        """Keep one link record per parent → child pair of these tasks: new
        pairs start as End to Start, removed pairs lose theirs."""
        # sudo: bookkeeping that follows the Parent / Child Tasks the user just changed
        Link = self.env['advanced.project.task.link'].sudo()
        tasks = self.sudo().exists()
        links = Link.search([('parent_id', 'in', tasks.ids)])
        existing = {(link.parent_id.id, link.child_id.id): link for link in links}
        wanted = {(task.id, child.id) for task in tasks for child in task.child_ids}
        Link.create([{'parent_id': parent, 'child_id': child} for parent, child in wanted - set(existing)])
        Link.browse([link.id for pair, link in existing.items() if pair not in wanted]).unlink()

    @api.model
    def _sync_all_links(self):
        """Link records for every existing parent → child pair (e.g. links made
        before link types existed)."""
        self.env.cr.execute("SELECT DISTINCT parent_id FROM advanced_project_task_link_rel")
        parents = self.sudo().browse([row[0] for row in self.env.cr.fetchall()])
        parents._sync_links()

    # ------------------------------------------------------------
    # Gantt chart
    # ------------------------------------------------------------

    @api.model
    def gantt_link_data(self, task_ids):
        """[{parent, child, type}] for the links between the given tasks."""
        tasks = self.browse(task_ids).exists()
        tasks.check_access('read')
        Link = self.env['advanced.project.task.link'].sudo()
        links = Link.search([('parent_id', 'in', tasks.ids), ('child_id', 'in', tasks.ids)])
        return [{'parent': link.parent_id.id, 'child': link.child_id.id, 'type': link.link_type} for link in links]

    @api.model
    def gantt_link_tasks(self, parent_id, child_id, link_type=DEFAULT_LINK_TYPE):
        """Link two tasks from the Gantt chart, the first becoming the parent,
        with the link's kind (dragged from the parent's start or end to the
        child's start or end). Returns the reschedule the Gantt chart offers
        when the child is scheduled too early for the link (see
        ``_gantt_reschedule_proposal``), or False."""
        if link_type not in dict(LINK_TYPES):
            raise ValueError(_('Unknown link type: %s', link_type))
        parent = self.browse(parent_id)
        parent.write({'child_ids': [(4, child_id)]})
        link = self._gantt_link(parent_id, child_id)
        link.link_type = link_type
        return link._gantt_reschedule_proposal()

    @api.model
    def gantt_reschedule_link(self, parent_id, child_id):
        """Move the child of a link (and the tasks linked after it, as far as
        needed) later so that it follows its parent. Tasks keep their
        length."""
        link = self._gantt_link(parent_id, child_id)
        for task, (first, last) in link._gantt_reschedule_plan().items():
            task = self.browse(task.id)  # written as the user (the plan is read as superuser)
            vals = {}
            if task.date_start:
                vals['date_start'] = first
            if task.date_end:
                vals['date_end'] = last
            task.write(vals)
        return True

    @api.model
    def _gantt_link(self, parent_id, child_id):
        parent = self.browse(parent_id)
        parent.check_access('read')
        # sudo: link records follow the tasks' Parent / Child Tasks, checked above
        return self.env['advanced.project.task.link'].sudo().search(
            [('parent_id', '=', parent_id), ('child_id', '=', child_id)], limit=1)

    def _gantt_span(self):
        """(first day, last day) of the task on the Gantt chart; a task with
        one date (e.g. a milestone) spans that day."""
        self.ensure_one()
        first = self.date_start or self.date_end
        return first, (self.date_end or self.date_start)


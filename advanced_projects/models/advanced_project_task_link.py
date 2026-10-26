from odoo import _, api, fields, models

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
        child's start or end)."""
        if link_type not in dict(LINK_TYPES):
            raise ValueError(_('Unknown link type: %s', link_type))
        parent = self.browse(parent_id)
        parent.write({'child_ids': [(4, child_id)]})
        link = self.env['advanced.project.task.link'].sudo().search(
            [('parent_id', '=', parent_id), ('child_id', '=', child_id)], limit=1)
        link.link_type = link_type
        return True

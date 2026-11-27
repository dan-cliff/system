from odoo import _, fields, models


def _actions_action(env, name, domain, context):
    action = env['ir.actions.act_window']._for_xml_id('advanced_actions_project.action_advanced_action_project')
    action.update({'name': name, 'domain': domain, 'context': context})
    return action


class AdvancedProject(models.Model):
    _inherit = 'advanced.project'

    action_ids = fields.One2many('advanced.action', 'project_id', string='Actions')
    action_count = fields.Integer('Action Count', compute='_compute_action_count')

    def _compute_action_count(self):
        Action = self.env['advanced.action']
        counts = {}
        if Action.has_access('read'):
            counts = dict(Action._read_group([('project_id', 'in', self.ids), ('state', 'in', ('open', 'in_progress'))],
                                             ['project_id'], ['__count']))
        for project in self:
            project.action_count = counts.get(project, 0)

    def action_open_actions(self):
        self.ensure_one()
        return _actions_action(self.env, _('%s – Actions', self.name), [('project_id', '=', self.id)],
                               {'default_project_id': self.id, 'search_default_open': 1})


class AdvancedProjectTask(models.Model):
    _inherit = 'advanced.project.task'

    action_ids = fields.One2many('advanced.action', 'project_task_id', string='Actions')
    action_count = fields.Integer('Action Count', compute='_compute_action_count')

    def _compute_action_count(self):
        Action = self.env['advanced.action']
        counts = {}
        if Action.has_access('read'):
            counts = dict(Action._read_group([('project_task_id', 'in', self.ids), ('state', 'in', ('open', 'in_progress'))],
                                             ['project_task_id'], ['__count']))
        for task in self:
            task.action_count = counts.get(task, 0)

    def action_open_actions(self):
        self.ensure_one()
        return _actions_action(self.env, _('%s – Actions', self.name), [('project_task_id', '=', self.id)],
                               {'default_project_id': self.project_id.id, 'default_project_task_id': self.id,
                                'search_default_open': 1})

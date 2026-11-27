from odoo import _, fields, models
from odoo.exceptions import UserError


def _checklist_counts(records, field_name, domain=()):
    Checklist = records.env['checklist.checklist']
    if not Checklist.has_access('read'):
        return {}
    return dict(Checklist._read_group([(field_name, 'in', records.ids), *domain], [field_name], ['__count']))


class AdvancedProjectTask(models.Model):
    _inherit = 'advanced.project.task'

    checklist_template_id = fields.Many2one(
        'checklist.template', string='Required Checklist', tracking=True, ondelete='restrict',
        domain=[('project_available', '=', True)],
        help='The checklist to complete for this task: completing it marks the task as done.')
    checklist_ids = fields.One2many('checklist.checklist', 'advanced_task_id', string='Checklists')
    checklist_count = fields.Integer('Checklist Count', compute='_compute_checklist_count')

    def _compute_checklist_count(self):
        counts = _checklist_counts(self, 'advanced_task_id')
        for task in self:
            task.checklist_count = counts.get(task, 0)

    def _checklist_values(self):
        """Values the task's Required Checklist starts with."""
        self.ensure_one()
        return {
            'template_id': self.checklist_template_id.id,
            'advanced_task_id': self.id,
            'company_id': self.company_id.id,
            'user_id': self.env.user.id,
            'date_due': self.date_end,
        }

    def action_start_checklist(self):
        """Open the task's Required Checklist: the one already started, or a
        new one."""
        self.ensure_one()
        if not self.checklist_template_id:
            raise UserError(_('Choose the Required Checklist for this task first.'))
        checklist = self.checklist_ids.filtered(
            lambda c: c.template_id == self.checklist_template_id and c.state == 'draft')[:1]
        if not checklist:
            checklist = self.env['checklist.checklist'].create(self._checklist_values())
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'checklist.checklist',
            'res_id': checklist.id,
            'views': [(False, 'form')],
            'target': 'current',
        }


class AdvancedProject(models.Model):
    _inherit = 'advanced.project'

    checklist_done_count = fields.Integer('Completed Checklists', compute='_compute_checklist_done_count')

    def _compute_checklist_done_count(self):
        counts = _checklist_counts(self, 'advanced_project_id', [('state', '=', 'done')])
        for project in self:
            project.checklist_done_count = counts.get(project, 0)

    def action_open_checklists(self):
        """The checklists of the project's tasks, filtered to the completed ones."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('checklists.action_checklist')
        action.update({
            'name': _('%s – Checklists', self.name),
            'domain': [('advanced_project_id', '=', self.id)],
            'context': {'search_default_done': 1, 'create': False},
        })
        return action

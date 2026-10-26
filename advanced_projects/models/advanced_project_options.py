"""Configurable choice lists, managed under Project > Configuration."""
from random import randint

from odoo import fields, models

# What a task stage means to the app: the Overview, Project Updates and Gantt
# chart sort tasks into outstanding / blocked / completed with it, so it stays
# a fixed selection (CLAUDE.md > Choice fields: technical states).
STAGE_CATEGORIES = [
    ('todo', 'To Do'),
    ('in_progress', 'In Progress'),
    ('blocked', 'Blocked'),
    ('done', 'Done'),
    ('cancelled', 'Cancelled'),
]
CLOSED_CATEGORIES = ('done', 'cancelled')


class AdvancedProjectTaskStage(models.Model):
    _name = 'advanced.project.task.stage'
    _description = 'Project Task Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    category = fields.Selection(
        STAGE_CATEGORIES, required=True, default='todo',
        help='What the stage means: tasks in a Blocked stage count as blocked, and tasks in a Done '
             'or Cancelled stage count as closed in the Overview, Project Updates and Gantt chart.')
    fold = fields.Boolean('Folded in Kanban')
    color = fields.Char('Colour', default='#3BB8FF')


class AdvancedProjectStage(models.Model):
    _name = 'advanced.project.stage'
    _description = 'Project Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_closed = fields.Boolean(
        'Closed', help='Projects in this stage are finished or cancelled; they are hidden from the '
                       'Active filter.')
    fold = fields.Boolean('Folded in Kanban')

    _name_uniq = models.Constraint('unique (name)', 'A project stage with this name already exists.')


class AdvancedProjectStatus(models.Model):
    _name = 'advanced.project.status'
    _description = 'Project Status'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Char('Colour', default='#14C9A5')

    _name_uniq = models.Constraint('unique (name)', 'A project status with this name already exists.')


class AdvancedProjectTag(models.Model):
    _name = 'advanced.project.tag'
    _description = 'Project Tag'
    _order = 'name'

    def _default_color(self):
        return randint(1, 11)

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(default=_default_color)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique (name)', 'A tag with this name already exists.')

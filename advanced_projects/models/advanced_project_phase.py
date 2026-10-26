from odoo import api, fields, models

from .advanced_project_options import CLOSED_CATEGORIES
from .advanced_project_task_filter import format_date


class AdvancedProjectPhase(models.Model):
    _name = 'advanced.project.phase'
    _description = 'Project Phase'
    _order = 'project_id, sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    project_id = fields.Many2one(
        'advanced.project', string='Project', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='project_id.company_id', store=True, index=True)
    description = fields.Text()
    color = fields.Char('Colour', default='#8E5CF0')
    task_ids = fields.One2many('advanced.project.task', 'phase_id', string='Tasks')
    date_start = fields.Date(
        'Start Date', compute='_compute_dates', store=True, help='The earliest start date of its tasks.')
    date_end = fields.Date('End Date', compute='_compute_dates', store=True, help='The latest end date of its tasks.')
    task_count = fields.Integer('Task Count', compute='_compute_progress', store=True)
    done_count = fields.Integer('Done Tasks', compute='_compute_progress', store=True)
    progress = fields.Float(compute='_compute_progress', store=True)

    @api.depends('task_ids.date_start', 'task_ids.date_end')
    def _compute_dates(self):
        for phase in self:
            starts = [d for d in phase.task_ids.mapped('date_start') if d]
            ends = [d for d in phase.task_ids.mapped('date_end') if d]
            phase.date_start = min(starts) if starts else False
            phase.date_end = max(ends + starts) if (ends or starts) else False

    @api.depends('task_ids.stage_category')
    def _compute_progress(self):
        for phase in self:
            tasks = phase.task_ids.filtered(lambda t: t.stage_category != 'cancelled')
            done = tasks.filtered(lambda t: t.stage_category == 'done')
            phase.task_count = len(tasks)
            phase.done_count = len(done)
            phase.progress = 100.0 * len(done) / len(tasks) if tasks else 0.0

    def _overview_values(self):
        return [{
            'id': phase.id,
            'name': phase.name,
            'color': phase.color or '#8E5CF0',
            'progress': round(phase.progress),
            'done': phase.done_count,
            'total': phase.task_count,
            'open': len(phase.task_ids.filtered(lambda t: t.stage_category not in CLOSED_CATEGORIES)),
            'date_start': format_date(phase.date_start),
            'date_end': format_date(phase.date_end),
        } for phase in self]

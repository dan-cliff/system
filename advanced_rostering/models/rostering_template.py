# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .rostering_tools import CYCLE_WEEKS, CYCLES, WEEKDAYS, get_cycle


class RosteringTemplate(models.Model):
    """A standard roster for one cycle. Each line is a shift on a weekday of
    a week of the cycle (week 1 being the first 7 days of the period)."""
    _name = 'rostering.template'
    _description = 'Roster Template'
    _order = 'sequence, name, id'

    name = fields.Char(string='Roster Template', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    cycle = fields.Selection(
        CYCLES, string='Cycle', required=True, readonly=True,
        default=lambda self: get_cycle(self.env),
        help='The publishing cycle in Settings when the template was made: how many weeks it holds.',
    )
    week_count = fields.Integer(string='Weeks', compute='_compute_week_count')
    line_ids = fields.One2many('rostering.template.line', 'template_id', string='Shifts', copy=True)
    line_count = fields.Integer(string='Shifts', compute='_compute_line_count')
    total_hours = fields.Float(string='Paid Hours', compute='_compute_line_count')
    description = fields.Text(string='Notes')
    company_id = fields.Many2one('res.company', string='Company', index=True,
                                 default=lambda self: self.env.company)

    @api.depends('cycle')
    def _compute_week_count(self):
        for template in self:
            template.week_count = CYCLE_WEEKS.get(template.cycle, 1)

    @api.depends('line_ids.paid_hours')
    def _compute_line_count(self):
        for template in self:
            template.line_count = len(template.line_ids)
            template.total_hours = sum(template.line_ids.mapped('paid_hours'))


class RosteringTemplateLine(models.Model):
    _name = 'rostering.template.line'
    _description = 'Roster Template Shift'
    _order = 'template_id, week, weekday, start_time, id'

    template_id = fields.Many2one('rostering.template', string='Roster Template', required=True,
                                  index=True, ondelete='cascade')
    week = fields.Integer(string='Week', required=True, default=1,
                          help='Week of the cycle: week 1 is the first 7 days of the roster period.')
    weekday = fields.Selection(WEEKDAYS, string='Day', required=True, default='0')
    user_id = fields.Many2one('res.users', string='User', index=True,
                              help='Leave empty for a shift to assign later.')
    person_name = fields.Char(string='Person', compute='_compute_person_name')
    standard_shift_id = fields.Many2one('rostering.standard.shift', string='Standard Shift',
                                        required=True, ondelete='restrict')
    duty_id = fields.Many2one(
        'rostering.duty', string='Duty', compute='_compute_duty_id', store=True, readonly=False,
        precompute=True,
    )
    start_time = fields.Float(related='standard_shift_id.start_time')
    end_time = fields.Float(related='standard_shift_id.end_time')
    paid_hours = fields.Float(related='standard_shift_id.paid_hours')
    note = fields.Char(string='Note')
    company_id = fields.Many2one(related='template_id.company_id', store=True)

    @api.depends('standard_shift_id')
    def _compute_duty_id(self):
        for line in self:
            if line.standard_shift_id.duty_id:
                line.duty_id = line.standard_shift_id.duty_id

    @api.depends('user_id.name')
    def _compute_person_name(self):
        for line in self:
            line.person_name = line.user_id.name or _('Unassigned')

    @api.constrains('week', 'template_id')
    def _check_week(self):
        for line in self:
            weeks = line.template_id.week_count
            if not 1 <= line.week <= weeks:
                raise ValidationError(_('A %(cycle)s template has weeks 1 to %(weeks)s.',
                                        cycle=dict(CYCLES)[line.template_id.cycle].lower(), weeks=weeks))

    def _prepare_shift_vals(self, roster, day):
        """Values of the shift this line makes on ``day`` of ``roster``."""
        self.ensure_one()
        return {
            'roster_id': roster.id,
            'date': day,
            'user_id': self.user_id.id,
            'standard_shift_id': self.standard_shift_id.id,
            'duty_id': self.duty_id.id,
            'note': self.note,
        }

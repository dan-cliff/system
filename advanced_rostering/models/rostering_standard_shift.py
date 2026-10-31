# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .rostering_tools import float_to_hhmm, span


class RosteringBreakMixin(models.AbstractModel):
    """A break in a shift, as hours of the day (e.g. 12.5 for 12:30)."""
    _name = 'rostering.break.mixin'
    _description = 'Rostering Break'
    _order = 'start_time, id'

    name = fields.Char(string='Break', required=True, default=lambda self: _('Break'))
    start_time = fields.Float(string='Start', required=True)
    end_time = fields.Float(string='End', required=True)
    paid = fields.Boolean(string='Paid', help='Paid breaks count towards the shift\'s paid hours.')
    duration = fields.Float(string='Duration', compute='_compute_duration', store=True)

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for brk in self:
            brk.duration = span(brk.start_time, brk.end_time)

    def _shift_times(self):
        """Start and end time of the shift the break belongs to."""
        raise NotImplementedError

    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        for brk in self:
            for value in (brk.start_time, brk.end_time):
                if not 0 <= value < 24:
                    raise ValidationError(_('Break times must be between 00:00 and 23:59.'))
            if not brk.duration:
                raise ValidationError(_('A break must end after it starts.'))
            shift_start, shift_end = brk._shift_times()
            offset = span(shift_start, brk.start_time)
            if offset + brk.duration > span(shift_start, shift_end):
                raise ValidationError(_(
                    'The break %(start)s – %(end)s is outside the shift (%(shift_start)s – %(shift_end)s).',
                    start=float_to_hhmm(brk.start_time), end=float_to_hhmm(brk.end_time),
                    shift_start=float_to_hhmm(shift_start), shift_end=float_to_hhmm(shift_end),
                ))

    def _copy_vals(self):
        return [{'name': brk.name, 'start_time': brk.start_time, 'end_time': brk.end_time, 'paid': brk.paid}
                for brk in self]


class RosteringShiftTimesMixin(models.AbstractModel):
    """Start, end and breaks of a shift, and the hours they make."""
    _name = 'rostering.shift.times.mixin'
    _description = 'Rostering Shift Times'

    start_time = fields.Float(string='Start', required=True, default=9.0)
    end_time = fields.Float(string='End', required=True, default=17.0,
                            help='A shift ending at or before its start time ends the next day.')
    duration = fields.Float(string='Length', compute='_compute_hours', store=True)
    break_hours = fields.Float(string='Unpaid Breaks', compute='_compute_hours', store=True)
    paid_hours = fields.Float(string='Paid Hours', compute='_compute_hours', store=True)
    times_label = fields.Char(string='Times', compute='_compute_times_label')

    def _breaks(self):
        raise NotImplementedError

    # Models using the mixin add @api.depends with their break field.
    def _compute_hours(self):
        for record in self:
            record.duration = span(record.start_time, record.end_time)
            record.break_hours = sum(record._breaks().filtered(lambda b: not b.paid).mapped('duration'))
            record.paid_hours = max(record.duration - record.break_hours, 0.0)

    @api.depends('start_time', 'end_time')
    def _compute_times_label(self):
        for record in self:
            record.times_label = '%s – %s' % (float_to_hhmm(record.start_time), float_to_hhmm(record.end_time))

    @api.constrains('start_time', 'end_time')
    def _check_shift_times(self):
        for record in self:
            for value in (record.start_time, record.end_time):
                if not 0 <= value < 24:
                    raise ValidationError(_('Shift times must be between 00:00 and 23:59.'))
            if not record.duration:
                raise ValidationError(_('A shift cannot start and end at the same time.'))
            record._breaks()._check_times()


class RosteringStandardShift(models.Model):
    _name = 'rostering.standard.shift'
    _inherit = ['rostering.shift.times.mixin']
    _description = 'Standard Shift'
    _order = 'sequence, start_time, name, id'

    name = fields.Char(string='Standard Shift', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Colour')
    duty_id = fields.Many2one('rostering.duty', string='Default Duty',
                              help='Duty given to shifts of this kind unless they pick another.')
    break_ids = fields.One2many('rostering.standard.shift.break', 'standard_shift_id', string='Breaks', copy=True)
    company_id = fields.Many2one('res.company', string='Company', index=True,
                                 help='Leave empty to offer the standard shift to every company.')

    def _breaks(self):
        return self.break_ids

    @api.depends('start_time', 'end_time', 'break_ids.duration', 'break_ids.paid')
    def _compute_hours(self):
        return super()._compute_hours()

    @api.depends('name', 'start_time', 'end_time')
    def _compute_display_name(self):
        for shift in self:
            shift.display_name = '%s (%s)' % (shift.name or '', shift.times_label)


class RosteringStandardShiftBreak(models.Model):
    _name = 'rostering.standard.shift.break'
    _inherit = ['rostering.break.mixin']
    _description = 'Standard Shift Break'

    standard_shift_id = fields.Many2one('rostering.standard.shift', string='Standard Shift',
                                        required=True, index=True, ondelete='cascade')

    def _shift_times(self):
        return self.standard_shift_id.start_time, self.standard_shift_id.end_time

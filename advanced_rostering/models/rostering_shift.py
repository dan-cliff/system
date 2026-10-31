# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .rostering_tools import float_to_hhmm, local_to_utc, period_bounds, search_positive


class RosteringShift(models.Model):
    _name = 'rostering.shift'
    _inherit = ['rostering.shift.times.mixin']
    _description = 'Shift'
    _order = 'date, start_time, person_name, id'

    roster_id = fields.Many2one('rostering.roster', string='Roster', required=True, index=True,
                                ondelete='cascade')
    roster_state = fields.Selection(related='roster_id.state', string='Roster Status', store=True, index=True)
    user_id = fields.Many2one('res.users', string='User', index=True,
                              help='Leave empty for an open shift to assign later.')
    person_name = fields.Char(string='Person', compute='_compute_person_name', store=True)
    is_assigned = fields.Boolean(string='Assigned', compute='_compute_person_name', store=True)
    date = fields.Date(string='Date', required=True, index=True, default=fields.Date.context_today)
    standard_shift_id = fields.Many2one('rostering.standard.shift', string='Standard Shift', index=True)
    duty_id = fields.Many2one('rostering.duty', string='Duty', index=True,
                              compute='_compute_from_standard_shift', store=True, readonly=False, precompute=True)
    # Follow the standard shift; default=None drops the mixin's defaults, which
    # would otherwise stop the compute on create.
    start_time = fields.Float(compute='_compute_from_standard_shift', store=True, readonly=False, precompute=True,
                              default=None)
    end_time = fields.Float(compute='_compute_from_standard_shift', store=True, readonly=False, precompute=True,
                            default=None)
    break_ids = fields.One2many('rostering.shift.break', 'shift_id', string='Breaks', copy=True)
    start_datetime = fields.Datetime(string='Starts', compute='_compute_datetimes', store=True, index=True)
    end_datetime = fields.Datetime(string='Ends', compute='_compute_datetimes', store=True)
    note = fields.Char(string='Note')
    color = fields.Integer(related='duty_id.color', string='Colour')
    company_id = fields.Many2one(related='roster_id.company_id', store=True, index=True)
    leave_id = fields.Many2one('rostering.leave', string='Approved Leave', compute='_compute_leave_id',
                               help='Approved leave of the person on this day.')
    on_leave = fields.Boolean(string='On Leave', compute='_compute_leave_id', search='_search_on_leave')
    is_mine = fields.Boolean(string='My Shifts', compute='_compute_is_mine', search='_search_is_mine')

    # ------------------------------------------------------------------
    # Whose shift it is. Personnel (advanced_rostering_hr) extends these.
    # ------------------------------------------------------------------
    @api.model
    def _person_field(self):
        """Field naming the person, shared with rostering.leave."""
        return 'user_id'

    @api.model
    def _my_domain(self):
        return [('user_id', '=', self.env.uid)]

    def _get_tz(self):
        self.ensure_one()
        return self.user_id.tz or self.env.user.tz or 'UTC'

    @api.depends('user_id.name')
    def _compute_person_name(self):
        for shift in self:
            shift.person_name = shift.user_id.name or _('Unassigned')
            shift.is_assigned = bool(shift.user_id)

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    def _breaks(self):
        return self.break_ids

    @api.depends('start_time', 'end_time', 'break_ids.duration', 'break_ids.paid')
    def _compute_hours(self):
        return super()._compute_hours()

    @api.depends('standard_shift_id')
    def _compute_from_standard_shift(self):
        for shift in self:
            standard = shift.standard_shift_id
            if standard:
                shift.start_time = standard.start_time
                shift.end_time = standard.end_time
                if standard.duty_id:
                    shift.duty_id = standard.duty_id
            elif not shift.start_time and not shift.end_time:
                shift.start_time, shift.end_time = 9.0, 17.0

    @api.depends('date', 'start_time', 'duration', 'user_id.tz')
    def _compute_datetimes(self):
        for shift in self:
            if not shift.date:
                shift.start_datetime = shift.end_datetime = False
                continue
            tz = shift._get_tz()
            shift.start_datetime = local_to_utc(shift.date, shift.start_time, tz)
            shift.end_datetime = local_to_utc(shift.date, shift.start_time + shift.duration, tz)

    @api.depends('user_id', 'person_name', 'duty_id', 'date', 'start_time', 'end_time')
    def _compute_display_name(self):
        for shift in self:
            parts = [shift.person_name, shift.date and shift.date.strftime('%d/%m/%Y'), shift.times_label,
                     shift.duty_id.name]
            shift.display_name = ' · '.join(part for part in parts if part)

    def _compute_leave_id(self):
        field = self._person_field()
        assigned = self.filtered(lambda shift: shift[field] and shift.date)
        leaves = self.env['rostering.leave'].sudo()
        if assigned:
            leaves = leaves.search([
                ('state', '=', 'approved'),
                (field, 'in', assigned[field].ids),
                ('date_from', '<=', max(assigned.mapped('date'))),
                ('date_to', '>=', min(assigned.mapped('date'))),
            ])
        by_person = leaves.grouped(field)
        for shift in self:
            shift.leave_id = next(
                (leave.id for leave in by_person.get(shift[field], [])
                 if shift in assigned and leave.date_from <= shift.date <= leave.date_to),
                False,
            )
            shift.on_leave = bool(shift.leave_id)

    def _search_on_leave(self, operator, value):
        positive = search_positive(operator, value)
        if positive is None:
            return NotImplemented
        field = self._person_field()
        leaves = self.env['rostering.leave'].sudo().search([('state', '=', 'approved'), (field, '!=', False)])
        ids = []
        for leave in leaves:
            ids += self.sudo().search([
                (field, '=', leave[field].id),
                ('date', '>=', leave.date_from),
                ('date', '<=', leave.date_to),
            ]).ids
        return [('id', 'in' if positive else 'not in', ids)]

    @api.depends_context('uid')
    def _compute_is_mine(self):
        mine = self.filtered_domain(self._my_domain())
        for shift in self:
            shift.is_mine = shift in mine

    def _search_is_mine(self, operator, value):
        positive = search_positive(operator, value)
        if positive is None:
            return NotImplemented
        domain = self._my_domain()
        if positive:
            return domain
        return [('id', 'not in', self.with_context(active_test=False).search(domain).ids)]

    # ------------------------------------------------------------------
    # Create / write
    # ------------------------------------------------------------------
    @api.onchange('standard_shift_id')
    def _onchange_standard_shift_id(self):
        if self.standard_shift_id:
            self.break_ids = [(5, 0, 0)] + [(0, 0, vals) for vals in self.standard_shift_id.break_ids._copy_vals()]

    @api.model_create_multi
    def create(self, vals_list):
        standard_shifts = self.env['rostering.standard.shift']
        for vals in vals_list:
            if vals.get('standard_shift_id') and 'break_ids' not in vals:
                standard = standard_shifts.browse(vals['standard_shift_id'])
                vals['break_ids'] = [(0, 0, brk) for brk in standard.break_ids._copy_vals()]
        shifts = super().create(vals_list)
        if not self.env.su:
            shifts.roster_id._check_can_edit()
        return shifts

    def write(self, vals):
        if not self.env.su:
            self.roster_id._check_can_edit()
        if vals.get('standard_shift_id') and 'break_ids' not in vals:
            # e.g. changed in the roster's shift list, which has no breaks column
            standard = self.env['rostering.standard.shift'].browse(vals['standard_shift_id'])
            vals = dict(vals, break_ids=[(5, 0, 0)] + [(0, 0, brk) for brk in standard.break_ids._copy_vals()])
        res = super().write(vals)
        if 'roster_id' in vals and not self.env.su:
            self.roster_id._check_can_edit()
        return res

    def unlink(self):
        if not self.env.su:
            self.roster_id._check_can_edit()
        return super().unlink()

    @api.constrains('date', 'roster_id')
    def _check_date(self):
        for shift in self:
            roster = shift.roster_id
            if not roster.date_start <= shift.date <= roster.date_end:
                raise ValidationError(_(
                    '%(day)s is outside the roster\'s period (%(start)s – %(end)s).',
                    day=shift.date.strftime('%d/%m/%Y'),
                    start=roster.date_start.strftime('%d/%m/%Y'),
                    end=roster.date_end.strftime('%d/%m/%Y'),
                ))

    # ------------------------------------------------------------------
    # My Roster and Leave (static/src/my_roster)
    # ------------------------------------------------------------------
    @api.model
    def _my_person_name(self):
        return self.env.user.name

    @api.model
    def _my_manager_name(self):
        """The logged-in user's Manager (with Personnel), shown on My Roster."""
        return False

    def _my_roster_values(self):
        """What My Roster and Leave shows of a shift."""
        self.ensure_one()
        return {
            'id': self.id,
            'start': float_to_hhmm(self.start_time),
            'end': float_to_hhmm(self.end_time),
            'overnight': self.start_time + self.duration >= 24,
            'duty': self.duty_id.name or '',
            'duty_color': self.duty_id.color or 0,
            'standard_shift': self.standard_shift_id.name or '',
            'breaks': ', '.join(
                '%s %s – %s%s' % (brk.name, float_to_hhmm(brk.start_time), float_to_hhmm(brk.end_time),
                                  _(' (paid)') if brk.paid else '')
                for brk in self.break_ids
            ),
            'paid_hours': self.paid_hours,
            'roster': self.roster_id.display_name,
            'note': self.note or '',
            'on_leave': self.on_leave,
            'extra': [],
        }

    @api.model
    def get_my_roster(self, offset=0):
        """The logged-in user's published shifts for the roster period
        ``offset`` periods from the current one, with their upcoming leave."""
        offset = int(offset or 0)
        today = fields.Date.context_today(self)
        start, end = period_bounds(self.env, today)
        for _step in range(abs(offset)):
            start, end = period_bounds(self.env, start - timedelta(days=1) if offset < 0 else end + timedelta(days=1))
        shifts = self.search(self._my_domain() + [
            ('roster_state', '=', 'published'),
            ('date', '>=', start),
            ('date', '<=', end),
        ], order='date, start_time, id')
        shifts_by_day = shifts.grouped('date')
        Leave = self.env['rostering.leave']
        period_leaves = Leave.search(Leave._my_domain() + [
            ('state', '=', 'approved'), ('date_from', '<=', end), ('date_to', '>=', start),
        ])
        days = []
        day = start
        while day <= end:
            day_shifts = shifts_by_day.get(day, self)
            days.append({
                'date': fields.Date.to_string(day),
                'weekday': day.strftime('%A'),
                'label': day.strftime('%d/%m/%Y'),
                'is_today': day == today,
                'is_past': day < today,
                'shifts': [shift._my_roster_values() for shift in day_shifts],
                'leave': [leave.leave_type_id.name for leave in period_leaves
                          if leave.date_from <= day <= leave.date_to],
            })
            day += timedelta(days=1)

        upcoming = Leave.search(Leave._my_domain() + [
            ('date_to', '>=', today), ('state', 'in', ('draft', 'submitted', 'approved')),
        ], order='date_from, id')
        states = dict(Leave._fields['state']._description_selection(self.env))
        return {
            'person': self._my_person_name(),
            'manager': self._my_manager_name(),
            'offset': offset,
            'start': start.strftime('%d/%m/%Y'),
            'end': end.strftime('%d/%m/%Y'),
            'days': days,
            'total_hours': sum(shifts.mapped('paid_hours')),
            'shift_count': len(shifts),
            'leaves': [{
                'id': leave.id,
                'type': leave.leave_type_id.name,
                'type_color': leave.leave_type_id.color or 0,
                'from': leave.date_from.strftime('%d/%m/%Y'),
                'to': leave.date_to.strftime('%d/%m/%Y'),
                'days': leave.duration_days,
                'state': leave.state,
                'state_label': states.get(leave.state, leave.state),
                'approver': leave.approver_user_id.name or '',
            } for leave in upcoming],
            'can_request': Leave.has_access('create'),
        }


class RosteringShiftBreak(models.Model):
    _name = 'rostering.shift.break'
    _inherit = ['rostering.break.mixin']
    _description = 'Shift Break'

    shift_id = fields.Many2one('rostering.shift', string='Shift', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='shift_id.company_id', store=True)

    def _shift_times(self):
        return self.shift_id.start_time, self.shift_id.end_time

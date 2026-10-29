import logging
from collections import defaultdict
from datetime import datetime, time, timedelta
from itertools import chain

import pytz
from dateutil.relativedelta import MO, SU, relativedelta
from dateutil.rrule import DAILY, rrule

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import float_is_zero
from odoo.tools.date_utils import sum_intervals
from odoo.tools.intervals import Intervals

from .attendance_alert import _day_bounds_utc

_logger = logging.getLogger(__name__)

# Alerts are for live arrivals and departures: back-dated edits (and offline
# events synced much later) do not send messages.
ALERT_MAX_AGE = timedelta(hours=12)

IN_MODES = [
    ('kiosk', 'Kiosk'),
    ('systray', 'Odoo'),
    ('manual', 'Manual'),
    ('technical', 'Technical'),
]
OUT_MODES = IN_MODES + [('auto_check_out', 'Automatic Sign Out')]


def _maps_url(latitude, longitude):
    return f'https://maps.google.com?q={latitude},{longitude}'


class AdvancedAttendance(models.Model):
    _name = 'advanced.attendance'
    _description = 'Attendance'
    _inherit = ['mail.thread']
    _order = 'check_in desc, id desc'
    _check_company_auto = True

    def _default_employee(self):
        return self.env.user.employee_id

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade', index=True,
        default=_default_employee, tracking=True,
        domain="[('company_id', 'in', allowed_company_ids)]",
    )
    department_id = fields.Many2one(related='employee_id.department_id', string='Department')
    manager_id = fields.Many2one(related='employee_id.parent_id', string='Manager')
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        compute='_compute_company_id', store=True, readonly=False, precompute=True,
    )
    check_in = fields.Datetime(
        string='Signed In', required=True, index=True, tracking=True, default=fields.Datetime.now,
    )
    check_out = fields.Datetime(string='Signed Out', tracking=True)
    date = fields.Date(compute='_compute_date', store=True, index=True, precompute=True)
    worked_hours = fields.Float(
        string='Worked Hours', compute='_compute_worked_hours', store=True, readonly=True,
        help='Time between signing in and out, less any lunch break in the working schedule.',
    )
    color = fields.Integer(compute='_compute_color')

    # ── Extra hours (overtime) ─────────────────────────────────────────────
    overtime_hours = fields.Float(
        string='Extra Hours', compute='_compute_overtime_hours', store=True,
        help='Hours worked beyond what the overtime rules of the employee\'s ruleset expect '
             '(negative for missing hours when Absence Management is on).',
    )
    overtime_status = fields.Selection(
        [('to_approve', 'To Approve'), ('approved', 'Approved'), ('refused', 'Refused')],
        string='Extra Hours Status', compute='_compute_overtime_status', store=True, tracking=True, readonly=False,
    )
    validated_overtime_hours = fields.Float(
        string='Approved Extra Hours', compute='_compute_validated_overtime_hours', store=True, readonly=True,
        tracking=True,
    )
    expected_hours = fields.Float(
        string='Regular Hours', compute='_compute_expected_hours', store=True, aggregator='sum',
    )
    linked_overtime_ids = fields.Many2many(
        'advanced.attendance.overtime.line', string='Extra Hours Details',
        compute='_compute_linked_overtime_ids', readonly=False,
    )
    can_approve_overtime = fields.Boolean(compute='_compute_can_approve_overtime')

    # ── How and where ──────────────────────────────────────────────────────
    in_mode = fields.Selection(IN_MODES, string='Signed In With', default='manual', readonly=True)
    in_latitude = fields.Float(string='Latitude', digits=(10, 7), readonly=True, aggregator=None)
    in_longitude = fields.Float(string='Longitude', digits=(10, 7), readonly=True, aggregator=None)
    in_location = fields.Char(string='Sign In Location', help='The kiosk, or the place worked out from the GPS position or IP address.')
    in_ip_address = fields.Char(string='IP Address', readonly=True)
    in_browser = fields.Char(string='Browser', readonly=True)
    out_mode = fields.Selection(OUT_MODES, string='Signed Out With', default='manual', readonly=True)
    out_latitude = fields.Float(string='Sign Out Latitude', digits=(10, 7), readonly=True, aggregator=None)
    out_longitude = fields.Float(string='Sign Out Longitude', digits=(10, 7), readonly=True, aggregator=None)
    out_location = fields.Char(string='Sign Out Location')
    out_ip_address = fields.Char(string='Sign Out IP Address', readonly=True)
    out_browser = fields.Char(string='Sign Out Browser', readonly=True)

    # ── Kiosks ─────────────────────────────────────────────────────────────
    in_kiosk_id = fields.Many2one(
        'advanced.attendance.kiosk', string='Signed In At', readonly=True, index=True, ondelete='set null',
    )
    out_kiosk_id = fields.Many2one(
        'advanced.attendance.kiosk', string='Signed Out At', readonly=True, ondelete='set null',
    )
    kiosk_work_location_id = fields.Many2one(
        'hr.work.location', string='Kiosk Work Location',
        compute='_compute_kiosk_work_location_id', store=True, index=True,
    )
    kiosk_out_work_location_id = fields.Many2one(
        'hr.work.location', string='Kiosk Sign Out Location',
        compute='_compute_kiosk_out_work_location_id', store=True, index=True,
    )
    kiosk_transferred = fields.Boolean(
        string='Signed Out by Signing In Elsewhere', readonly=True,
        help='Signed out because the worker signed in at another kiosk.',
    )
    kiosk_offline_in = fields.Boolean(string='Signed In Offline', readonly=True)
    kiosk_offline_out = fields.Boolean(string='Signed Out Offline', readonly=True)
    # Ids of the offline kiosk events that created / closed this attendance, so
    # an event that is synced twice is only applied once.
    kiosk_event_in = fields.Char(readonly=True, copy=False, index='btree_not_null')
    kiosk_event_out = fields.Char(readonly=True, copy=False, index='btree_not_null')
    kiosk_response_ids = fields.One2many(
        'advanced.attendance.kiosk.response', 'attendance_id', string='Questionnaire Responses',
    )

    # ── Computes ───────────────────────────────────────────────────────────
    @api.depends('employee_id')
    def _compute_company_id(self):
        for attendance in self:
            attendance.company_id = attendance.employee_id.company_id or attendance.company_id or self.env.company

    @api.depends('check_in', 'employee_id')
    def _compute_date(self):
        for attendance in self:
            if not attendance.check_in:
                attendance.date = fields.Date.context_today(attendance)
                continue
            tz = pytz.timezone(attendance.employee_id._get_tz() if attendance.employee_id else 'UTC')
            attendance.date = pytz.utc.localize(attendance.check_in).astimezone(tz).date()

    @api.depends('worked_hours', 'overtime_hours')
    def _compute_expected_hours(self):
        for attendance in self:
            attendance.expected_hours = attendance.worked_hours - attendance.overtime_hours

    @api.depends('check_in', 'check_out', 'employee_id')
    def _compute_overtime_status(self):
        for attendance in self:
            if not attendance.linked_overtime_ids:
                attendance.overtime_status = False
            elif all(attendance.linked_overtime_ids.mapped(lambda ot: ot.status == 'approved')):
                attendance.overtime_status = 'approved'
            elif all(attendance.linked_overtime_ids.mapped(lambda ot: ot.status == 'refused')):
                attendance.overtime_status = 'refused'
            else:
                attendance.overtime_status = 'to_approve'

    @api.depends('check_in', 'check_out', 'employee_id')
    def _compute_overtime_hours(self):
        for attendance in self:
            attendance.overtime_hours = sum(attendance.linked_overtime_ids.mapped('duration'))

    @api.depends('check_in', 'check_out', 'employee_id')
    def _compute_validated_overtime_hours(self):
        for attendance in self:
            attendance.validated_overtime_hours = sum(attendance.linked_overtime_ids.filtered_domain(
                [('status', '=', 'approved')]).mapped('manual_duration'))

    @api.depends('check_in', 'check_out', 'employee_id')
    def _compute_linked_overtime_ids(self):
        overtimes = self._linked_overtimes().grouped(lambda ot: (ot.employee_id, ot.time_start))
        for attendance in self:
            attendance.linked_overtime_ids = overtimes.get((attendance.employee_id, attendance.check_in), False)

    @api.depends_context('uid')
    def _compute_can_approve_overtime(self):
        can_approve = self.env.user.has_group('advanced_attendance.group_attendance_approve')
        for attendance in self:
            attendance.can_approve_overtime = can_approve

    @api.depends('check_in', 'check_out', 'employee_id')
    def _compute_worked_hours(self):
        for attendance in self:
            if attendance.check_in and attendance.check_out and attendance.employee_id:
                attendance.worked_hours = attendance._worked_hours_in_range(attendance.check_in, attendance.check_out)
            else:
                attendance.worked_hours = False

    def _worked_hours_in_range(self, start, end):
        """Hours worked between naive UTC ``start`` and ``end``, less the lunch
        breaks of the employee's working schedule (as Odoo's Attendances app does)."""
        self.ensure_one()
        employee = self.employee_id
        calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
        tz = pytz.timezone((calendar.tz if calendar else employee.resource_id.tz) or 'UTC')
        start_tz = pytz.utc.localize(max(self.check_in, start)).astimezone(tz)
        end_tz = pytz.utc.localize(min(self.check_out, end)).astimezone(tz)
        if end_tz < start_tz:
            return 0.0
        lunch = []
        if employee.resource_id and not employee.resource_id._is_flexible():
            lunch = employee._employee_attendance_intervals(start_tz, end_tz, lunch=True)
        return sum_intervals(Intervals([(start_tz, end_tz, self)]) - lunch)

    def _compute_color(self):
        yesterday = fields.Datetime.now() - timedelta(days=1)
        for attendance in self:
            if attendance.check_out:
                attendance.color = 1 if attendance.worked_hours > 16 or attendance.out_mode == 'technical' else 0
            else:
                attendance.color = 1 if attendance.check_in < yesterday else 10

    @api.depends('employee_id', 'check_in', 'check_out')
    @api.depends_context('tz')
    def _compute_display_name(self):
        tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')

        def local(dt, fmt):
            return pytz.utc.localize(dt).astimezone(tz).strftime(fmt)

        for attendance in self:
            if not attendance.check_in:
                attendance.display_name = attendance.employee_id.name or _('New')
                continue
            start = local(attendance.check_in, '%d/%m/%Y %H:%M')
            if attendance.check_out:
                end = local(attendance.check_out, '%H:%M' if attendance.check_out - attendance.check_in < timedelta(hours=20)
                            else '%d/%m/%Y %H:%M')
                attendance.display_name = f'{attendance.employee_id.name}: {start} - {end}'
            else:
                attendance.display_name = _('%(employee)s: since %(start)s', employee=attendance.employee_id.name, start=start)

    @api.depends('in_kiosk_id')
    def _compute_kiosk_work_location_id(self):
        # Keep the location the worker signed in at, even if the kiosk moves later.
        for attendance in self:
            attendance.kiosk_work_location_id = (
                attendance.kiosk_work_location_id or attendance.in_kiosk_id.work_location_id
            )

    @api.depends('out_kiosk_id', 'kiosk_work_location_id')
    def _compute_kiosk_out_work_location_id(self):
        for attendance in self:
            attendance.kiosk_out_work_location_id = (
                attendance.out_kiosk_id.work_location_id or attendance.kiosk_work_location_id
            )

    # ── Constraints ────────────────────────────────────────────────────────
    @api.constrains('check_in', 'check_out')
    def _check_check_out_after_check_in(self):
        for attendance in self:
            if attendance.check_out and attendance.check_out < attendance.check_in:
                raise ValidationError(_('"Signed Out" cannot be earlier than "Signed In".'))

    @api.constrains('check_in', 'check_out', 'employee_id')
    def _check_overlap(self):
        """An employee has at most one open attendance, and attendances never overlap."""
        Attendance = self.env['advanced.attendance'].sudo()
        for attendance in self:
            employee = attendance.employee_id
            others = [('employee_id', '=', employee.id), ('id', '!=', attendance.id)]
            before = Attendance.search(others + [('check_in', '<=', attendance.check_in)], order='check_in desc', limit=1)
            if before and (not before.check_out or before.check_out > attendance.check_in):
                raise ValidationError(_(
                    '%(employee)s was already signed in at %(time)s.',
                    employee=employee.name, time=attendance._format_local(before.check_in),
                ))
            if not attendance.check_out:
                open_attendance = Attendance.search(others + [('check_out', '=', False)], limit=1)
                if open_attendance:
                    raise ValidationError(_(
                        '%(employee)s has not signed out since %(time)s.',
                        employee=employee.name, time=attendance._format_local(open_attendance.check_in),
                    ))
            else:
                inside = Attendance.search(others + [
                    ('check_in', '>', attendance.check_in), ('check_in', '<', attendance.check_out),
                ], order='check_in', limit=1)
                if inside:
                    raise ValidationError(_(
                        '%(employee)s was already signed in at %(time)s.',
                        employee=employee.name, time=attendance._format_local(inside.check_in),
                    ))

    def _format_local(self, dt):
        """Naive UTC datetime -> dd/mm/yyyy HH:MM in the employee's timezone."""
        self.ensure_one()
        tz = pytz.timezone(self.employee_id._get_tz() or 'UTC')
        return pytz.utc.localize(dt).astimezone(tz).strftime('%d/%m/%Y %H:%M')

    # ── CRUD ───────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        attendances = super().create(vals_list)
        attendances._update_overtime()
        attendances._alert_notify('in')
        attendances.filtered('check_out')._alert_notify('out')
        return attendances

    def write(self, vals):
        open_before = self.filtered(lambda a: not a.check_out) if vals.get('check_out') else self.browse()
        domain_pre = self._get_overtimes_to_update_domain()
        result = super().write(vals)
        if any(field in vals for field in ('employee_id', 'check_in', 'check_out')):
            # Recompute the extra hours of the days before and after the change,
            # in case the attendance moved to another day.
            self._update_overtime(Domain.OR([domain_pre, self._get_overtimes_to_update_domain()]))
        open_before.filtered('check_out')._alert_notify('out')
        return result

    def unlink(self):
        domain = self._get_overtimes_to_update_domain()
        result = super().unlink()
        self.exists()._update_overtime(domain)
        return result

    def copy(self, default=None):
        raise UserError(_('You cannot duplicate an attendance.'))

    # ── Actions ────────────────────────────────────────────────────────────
    def _linked_overtimes(self):
        return self.env['advanced.attendance.overtime.line'].search([
            ('time_start', 'in', self.mapped('check_in')),
            ('employee_id', 'in', self.employee_id.ids),
        ])

    def action_approve_overtime(self):
        self._check_can_approve_overtime()
        self.sudo().linked_overtime_ids.action_approve()

    def action_refuse_overtime(self):
        self._check_can_approve_overtime()
        self.sudo().linked_overtime_ids.action_refuse()

    def action_manual_sign_out(self):
        """Sign people out now from the On Site Now board, e.g. during an evacuation.
        Needs the "Attendances: Manual Sign Out" permission; only attendances the user
        can see, and only those still open."""
        if not self.env.user.has_group('advanced_attendance.group_attendance_manual_sign_out'):
            raise AccessError(_('You are not allowed to sign people out.'))
        self.check_access('read')
        now = fields.Datetime.now()
        open_attendances = self.filtered(lambda a: not a.check_out)
        for attendance in open_attendances.sudo():
            attendance.write({'check_out': max(now, attendance.check_in), 'out_mode': 'manual'})
            attendance.message_post(body=_('Signed out manually by %s.', self.env.user.name))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Signed out: %s', ', '.join(open_attendances.employee_id.mapped('name')))
                if open_attendances else _('Nobody to sign out.'),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _check_can_approve_overtime(self):
        """Approving extra hours is the "Attendances: Approve Extra Hours" permission,
        on the attendances the user can see."""
        if not self.env.user.has_group('advanced_attendance.group_attendance_approve'):
            raise AccessError(_('You are not allowed to approve or refuse extra hours.'))
        self.check_access('read')

    def action_in_attendance_maps(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': _maps_url(self.in_latitude, self.in_longitude), 'target': 'new'}

    def action_out_attendance_maps(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': _maps_url(self.out_latitude, self.out_longitude), 'target': 'new'}

    # ── Automatic sign out ─────────────────────────────────────────────────
    def _auto_sign_out_due(self):
        """When this open attendance is signed out automatically (naive UTC), or None.

        Kiosk sign ins follow their kiosk's setting; other sign ins follow the
        company's On Site setting.
        """
        self.ensure_one()
        if self.in_kiosk_id:
            return self.in_kiosk_id._kiosk_auto_sign_out_due(self.check_in)
        company = self.company_id
        if company.onsite_auto_sign_out and company.onsite_auto_sign_out_hours > 0:
            return self.check_in + timedelta(hours=company.onsite_auto_sign_out_hours)
        return None

    @api.model
    def _cron_auto_sign_out(self):
        now = fields.Datetime.now()
        attendances = self.sudo().search([
            ('check_out', '=', False),
            '|', ('in_kiosk_id.auto_sign_out', '=', True),
            '&', ('in_kiosk_id', '=', False), ('company_id.onsite_auto_sign_out', '=', True),
        ])
        for attendance in attendances:
            due = attendance._auto_sign_out_due()
            if not due or due > now:
                continue
            try:
                with self.env.cr.savepoint():
                    if attendance.in_kiosk_id:
                        attendance.in_kiosk_id._kiosk_apply_auto_sign_out(attendance, due)
                    else:
                        attendance._apply_auto_sign_out(due)
            except Exception:
                _logger.exception('Automatic sign out failed for attendance %s', attendance.id)

    def _apply_auto_sign_out(self, due):
        self.ensure_one()
        self.sudo().write({'check_out': max(due, self.check_in), 'out_mode': 'auto_check_out'})
        self.sudo().message_post(body=_(
            'Automatically signed out at %s.', self._format_local(self.check_out),
        ))

    # ── Sign in / out alerts ───────────────────────────────────────────────
    def _alert_notify(self, direction):
        if self.env.context.get('onsite_no_alerts'):
            return
        now = fields.Datetime.now()
        recent = self.filtered(lambda a: now - ALERT_MAX_AGE <= (
            a.check_in if direction == 'in' else a.check_out) <= now + timedelta(minutes=5))
        if recent:
            self.env['advanced.attendance.alert']._alert_dispatch(recent, direction)

    def _alert_site(self, direction):
        self.ensure_one()
        site = self.kiosk_work_location_id if direction == 'in' else self.kiosk_out_work_location_id
        return site or self.employee_id.work_location_id

    def _alert_site_domain(self, site, field):
        """Attendances at ``site``. Attendances not made at a kiosk count as at the
        employee's own work location."""
        if self.employee_id.work_location_id == site:
            return ['|', (field, '=', site.id), (field, '=', False)]
        return [(field, '=', site.id)]

    def _alert_events(self, direction):
        """Which alert events this sign in or sign out is.

        :return: ``(set of event codes, site, naive UTC time)``
        """
        self.ensure_one()
        Attendance = self.env['advanced.attendance'].sudo()
        employee = self.employee_id
        tz = pytz.timezone(employee._get_tz())
        site = self._alert_site(direction)
        when = self.check_in if direction == 'in' else self.check_out
        day_start, _day_end = _day_bounds_utc(when, tz)
        others = [('employee_id', '=', employee.id), ('id', '!=', self.id)]
        if direction == 'in':
            events = {'in_every'}
            earlier = others + [('check_in', '<', when)]
            today = earlier + [('check_in', '>=', day_start)]
            if not Attendance.search_count(today, limit=1):
                events.add('in_first_today')
            if site:
                at_site = self._alert_site_domain(site, 'kiosk_work_location_id')
                if not Attendance.search_count(earlier + at_site, limit=1):
                    events.add('in_first_site')
                if not Attendance.search_count(today + at_site, limit=1):
                    events.add('in_first_site_today')
        else:
            events = {'out_every'}
            today = others + [('check_out', '!=', False), ('check_out', '<', when), ('check_out', '>=', day_start)]
            if not Attendance.search_count(today, limit=1):
                events.add('out_first_today')
            if site:
                at_site = self._alert_site_domain(site, 'kiosk_out_work_location_id')
                if not Attendance.search_count(today + at_site, limit=1):
                    events.add('out_first_site_today')
        return events, site, when

    # ── Extra hours (ported from Odoo's Attendances app) ───────────────────
    def _get_week_date_range(self):
        assert self
        dates = self.mapped('date')
        date_start, date_end = min(dates), max(dates)
        date_start = date_start - relativedelta(days=date_start.weekday())
        date_end = date_end + relativedelta(days=6 - date_end.weekday())
        return date_start, date_end

    def _get_overtimes_to_update_domain(self):
        if not self:
            return Domain.FALSE
        domain_list = []
        for employee, attendances in self.filtered(lambda att: att.check_out).grouped('employee_id').items():
            tz = pytz.timezone(employee.tz or 'UTC')
            local_check_in = pytz.utc.localize(min(attendances.mapped('check_in'))).astimezone(tz)
            local_check_out = pytz.utc.localize(max(attendances.mapped('check_out'))).astimezone(tz)
            versions = attendances.mapped(lambda att: att.employee_id.sudo()._get_version(att.date))
            rulesets = versions.onsite_ruleset_id
            # Whole weeks for weekly rules, or flexible daily rules capped weekly.
            if (
                any(rule.quantity_period == 'week' for rule in rulesets.sudo().rule_ids)
                or any(
                    version.resource_calendar_id.flexible_hours
                    and version.resource_calendar_id.hours_per_week
                    and any(
                        rule.base_off == 'quantity'
                        and rule.quantity_period == 'day'
                        and rule.expected_hours_from_contract
                        for rule in version.onsite_ruleset_id.sudo().rule_ids
                    )
                    for version in versions
                )
            ):
                date_from = local_check_in.date() + relativedelta(weekday=MO(-1))
                date_to = local_check_out.date() + relativedelta(weekday=SU)
            else:
                date_from = local_check_in.date()
                date_to = local_check_out.date()
            domain_list.append(Domain.AND([
                Domain('employee_id', '=', employee.id),
                Domain('check_in', '<=', tz.localize(datetime.combine(date_to, datetime.max.time()))
                       .astimezone(pytz.utc).replace(tzinfo=None)),
                Domain('check_out', '>', tz.localize(datetime.combine(date_from, datetime.min.time()))
                       .astimezone(pytz.utc).replace(tzinfo=None)),
            ]))
        if not domain_list:
            return Domain.FALSE
        return Domain.OR(domain_list) if len(domain_list) > 1 else domain_list[0]

    def _get_overtime_domain_from_attendance_domain(self, attendance_domain):
        overtime_domain = []
        for leaf in attendance_domain:
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3:
                field, operator, value = leaf
                if field == 'check_in':
                    field = 'time_start'
                elif field == 'check_out':
                    field = 'time_stop'
                overtime_domain.append((field, operator, value))
            else:
                overtime_domain.append(leaf)
        return overtime_domain

    def _update_overtime(self, attendance_domain=None):
        """Regenerate the extra hours of these attendances and the others on the same days
        (or weeks), from the overtime rules of each employee's ruleset."""
        if not attendance_domain:
            attendance_domain = self._get_overtimes_to_update_domain()
        Line = self.env['advanced.attendance.overtime.line'].sudo()
        all_overtime_lines = Line.search(self._get_overtime_domain_from_attendance_domain(attendance_domain))
        manual_overtimes = set(all_overtime_lines.filtered(
            lambda line: line.manual_duration != line.duration or line.status == 'to_approve'
        ).mapped(lambda line: (line.employee_id.id, line.date)))
        all_overtime_lines.unlink()
        all_attendances = (self | self.env['advanced.attendance'].sudo().search(attendance_domain)).filtered_domain(
            [('check_out', '!=', False)])
        if not all_attendances:
            return

        start_check_in = min(all_attendances.mapped('check_in')).date() - relativedelta(days=1)  # for timezone
        min_check_in = pytz.utc.localize(datetime.combine(start_check_in, datetime.min.time()))
        start_check_out = max(all_attendances.mapped('check_out')).date() + relativedelta(days=1)
        max_check_out = pytz.utc.localize(datetime.combine(start_check_out, datetime.max.time()))  # for timezone

        version_periods_by_employee = all_attendances.employee_id.sudo()._get_version_periods(min_check_in, max_check_out)
        attendances_by_ruleset = defaultdict(lambda: self.env['advanced.attendance'])
        for employee, emp_attendances in all_attendances.grouped('employee_id').items():
            for attendance in emp_attendances:
                ruleset_sudo = employee.sudo()._get_version(attendance._get_localized_times()[0]).onsite_ruleset_id
                if ruleset_sudo:
                    attendances_by_ruleset[ruleset_sudo] += attendance
        employees = all_attendances.employee_id
        schedules_intervals_by_employee = employees._get_schedules_by_employee_by_work_type(
            min_check_in, max_check_out, version_periods_by_employee)
        overtime_vals_list = []
        for ruleset_sudo, ruleset_attendances in attendances_by_ruleset.items():
            attendances_dates = list(chain(*ruleset_attendances._get_dates().values()))
            overtime_vals_list.extend([
                {**val, 'status': 'to_approve'} if (val['employee_id'], val['date']) in manual_overtimes else val
                for val in ruleset_sudo.rule_ids._generate_overtime_vals(
                    min(attendances_dates), max(attendances_dates), ruleset_attendances, schedules_intervals_by_employee)
            ])
        Line.create(overtime_vals_list)
        all_attendances.invalidate_recordset(['linked_overtime_ids'])
        for field in ('overtime_hours', 'expected_hours', 'validated_overtime_hours', 'overtime_status'):
            self.env.add_to_compute(self._fields[field], all_attendances)

    @api.model
    def _cron_absence_detection(self):
        """Add technical attendances on yesterday's missed working days, so they show as
        negative extra hours (Settings > On Site > Absence Management)."""
        yesterday = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0) - relativedelta(days=1)
        companies = self.env['res.company'].search([('onsite_absence_management', '=', True)])
        if not companies:
            return
        checked_in_employees = self.env['advanced.attendance.overtime.line'].sudo().search(
            [('date', '=', yesterday.date())]).employee_id
        absent_employees = self.env['hr.employee'].sudo().search([
            ('id', 'not in', checked_in_employees.ids),
            ('company_id', 'in', companies.ids),
            ('resource_calendar_id.flexible_hours', '=', False),
            ('current_version_id.contract_date_start', '<=', fields.Date.today() - relativedelta(days=1)),
        ])
        # Only days with scheduled work can be absences, whatever the period of the quantity rules
        start = pytz.utc.localize(yesterday - relativedelta(days=1))  # for timezone
        stop = pytz.utc.localize(yesterday + relativedelta(days=2))  # for timezone
        version_periods_by_employee = absent_employees._get_version_periods(start, stop)
        schedules_by_employee = absent_employees._get_schedules_by_employee_by_work_type(
            start, stop, version_periods_by_employee)
        yesterday_interval = Intervals([(yesterday, yesterday + relativedelta(days=1), self.env['resource.calendar'])])
        absent_employees = absent_employees.filtered(
            lambda emp: schedules_by_employee['schedule'][emp]['work'] & yesterday_interval)

        vals_list = []
        for employee in absent_employees:
            check_in = pytz.timezone(employee._get_tz()).localize(yesterday).astimezone(pytz.utc).replace(tzinfo=None)
            vals_list.append({
                'check_in': check_in,
                'check_out': check_in + relativedelta(seconds=1),
                'in_mode': 'technical',
                'out_mode': 'technical',
                'employee_id': employee.id,
            })
        technical = self.sudo().with_context(onsite_no_alerts=True).create(vals_list)
        to_unlink = technical.filtered(lambda a: float_is_zero(a.overtime_hours, 3))
        for attendance in technical - to_unlink:
            attendance.message_post(body=_('This attendance was created automatically to record an absence on that day.'))
        to_unlink.unlink()

    def _get_localized_times(self):
        self.ensure_one()
        tz = pytz.timezone(self.employee_id.sudo()._get_version(self.check_in.date()).tz or 'UTC')
        localized_start = pytz.utc.localize(self.check_in).astimezone(tz).replace(tzinfo=None)
        localized_end = pytz.utc.localize(self.check_out).astimezone(tz).replace(tzinfo=None)
        return localized_start, localized_end

    def _get_dates(self):
        result = {}
        for attendance in self:
            localized_start, localized_end = attendance._get_localized_times()
            result[attendance] = list(rrule(DAILY, dtstart=localized_start.date(), until=localized_end.date()))
        return result

    def _get_attendance_by_periods_by_employee(self):
        by_day = defaultdict(lambda: defaultdict(lambda: Intervals([], keep_distinct=True)))
        by_week = defaultdict(lambda: defaultdict(lambda: Intervals([], keep_distinct=True)))
        for attendance in self.sorted('check_in'):
            employee = attendance.employee_id
            check_in, check_out = attendance._get_localized_times()
            for day in rrule(dtstart=check_in.date(), until=check_out.date(), freq=DAILY):
                week_date = day + relativedelta(days=6 - day.weekday())
                start_datetime = datetime.combine(day, time.min)
                day_interval = Intervals([(start_datetime, datetime.combine(day, time.max), self.env['resource.calendar'])])
                week_interval = Intervals([(start_datetime, datetime.combine(week_date, time.max), self.env['resource.calendar'])])
                attendance_interval = Intervals([(check_in, check_out, attendance)])
                if intersected := attendance_interval & day_interval:
                    by_day[employee][day] |= intersected
                if intersected := attendance_interval & week_interval:
                    by_week[employee][week_date] |= intersected
        return {'day': by_day, 'week': by_week}

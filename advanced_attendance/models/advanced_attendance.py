import logging
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
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

    # ── How and where ──────────────────────────────────────────────────────
    in_mode = fields.Selection(IN_MODES, string='Signed In With', default='manual', readonly=True)
    in_latitude = fields.Float(string='Latitude', digits=(10, 7), readonly=True, aggregator=None)
    in_longitude = fields.Float(string='Longitude', digits=(10, 7), readonly=True, aggregator=None)
    in_location = fields.Char(string='Location', help='The kiosk, or the place worked out from the GPS position or IP address.')
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
        attendances._alert_notify('in')
        attendances.filtered('check_out')._alert_notify('out')
        return attendances

    def write(self, vals):
        open_before = self.filtered(lambda a: not a.check_out) if vals.get('check_out') else self.browse()
        result = super().write(vals)
        open_before.filtered('check_out')._alert_notify('out')
        return result

    def copy(self, default=None):
        raise UserError(_('You cannot duplicate an attendance.'))

    # ── Actions ────────────────────────────────────────────────────────────
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

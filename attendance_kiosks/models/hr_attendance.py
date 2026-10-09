from datetime import timedelta

import pytz

from odoo import api, fields, models

from .attendance_alert import _day_bounds_utc

# Alerts are for live arrivals and departures: back-dated edits (and offline
# events synced much later) do not send messages.
ALERT_MAX_AGE = timedelta(hours=12)


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    in_kiosk_id = fields.Many2one(
        'attendance.kiosk', string='Signed In At', readonly=True, index=True, ondelete='set null',
    )
    out_kiosk_id = fields.Many2one(
        'attendance.kiosk', string='Signed Out At', readonly=True, ondelete='set null',
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
        'attendance.kiosk.response', 'attendance_id', string='Questionnaire Responses',
    )

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

    # ── Sign in / out alerts ───────────────────────────────────────────────
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

    def _alert_notify(self, direction):
        now = fields.Datetime.now()
        recent = self.filtered(lambda a: now - ALERT_MAX_AGE <= (
            a.check_in if direction == 'in' else a.check_out) <= now + timedelta(minutes=5))
        if recent:
            self.env['attendance.alert']._alert_dispatch(recent, direction)

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
        Attendance = self.env['hr.attendance'].sudo()
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

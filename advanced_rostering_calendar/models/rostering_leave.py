# -*- coding: utf-8 -*-
from datetime import datetime, time

from markupsafe import Markup, escape

from odoo import api, fields, models

# Requests shown in Calendar; refused and cancelled ones are taken out.
CALENDAR_STATES = ('draft', 'submitted', 'approved')
# Changes to these fields update the leave's calendar event.
CALENDAR_FIELDS = {
    'state', 'leave_type_id', 'date_from', 'date_to', 'request_unit', 'datetime_from', 'datetime_to',
    'user_id', 'employee_id', 'reason', 'company_id',
    'org_division_id', 'org_business_unit_id', 'org_location_id', 'org_department_id',
}


class RosteringLeave(models.Model):
    _inherit = 'rostering.leave'

    calendar_event_id = fields.Many2one('calendar.event', string='Calendar Event', readonly=True, copy=False,
                                        index='btree_not_null', ondelete='set null')

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        leaves._sync_calendar_event()
        return leaves

    def write(self, vals):
        res = super().write(vals)
        if CALENDAR_FIELDS & set(vals):
            self._sync_calendar_event()
        return res

    def unlink(self):
        events = self.sudo().calendar_event_id
        res = super().unlink()
        events.with_context(rostering_calendar_sync=True).unlink()
        return res

    # ------------------------------------------------------------------
    # Calendar event
    # ------------------------------------------------------------------
    def _calendar_partners(self):
        """Contacts whose calendars show the leave: the person (their user,
        or the employee's work contact for an employee without one)."""
        self.ensure_one()
        partners = self._person_users().partner_id
        employee = self['employee_id'] if 'employee_id' in self._fields else None
        if employee and not partners and employee.work_contact_id:
            partners = employee.sudo().work_contact_id
        return partners

    def _calendar_event_values(self):
        self.ensure_one()
        group = self.env.ref('advanced_rostering_calendar.partner_leave_requests_calendar')
        state = dict(self._fields['state']._description_selection(self.env))[self.state]
        partners = self._calendar_partners() | group
        description = escape(self.reason or '')
        values = {
            'name': '%s: %s (%s)' % (self.person_name or '', self.leave_type_id.name or '', state),
            'res_model_id': self.env['ir.model']._get_id(self._name),
            'res_id': self.id,
            'user_id': (self._person_users()[:1] or self.env.user).id,
            'partner_ids': [(6, 0, partners.ids)],
            'show_as': 'busy',
            'privacy': 'public',
            'description': Markup('<p>%s</p>') % description if description else False,
        }
        # Same Organisation as the request (org_structure), not the units of
        # whoever happened to create it, so scoping treats both alike.
        event_fields = self.env['calendar.event']._fields
        for name in ('org_division_id', 'org_business_unit_id', 'org_location_id', 'org_department_id'):
            if name in event_fields and name in self._fields:
                values[name] = self[name].id
        if self.request_unit == 'partial' and self.datetime_from and self.datetime_to:
            values.update(allday=False, start=self.datetime_from, stop=self.datetime_to)
        else:
            # All-day events keep their dates in start / stop (08:00 - 18:00 by Calendar's convention).
            values.update(allday=True,
                          start=datetime.combine(self.date_from, time(8, 0)),
                          stop=datetime.combine(self.date_to, time(18, 0)))
        return values

    def _sync_calendar_event(self):
        """Create, update or remove each request's calendar event."""
        Event = self.env['calendar.event'].sudo().with_context(
            rostering_calendar_sync=True, dont_notify=True, no_mail_to_attendees=True,
            mail_create_nolog=True, mail_notrack=True, tracking_disable=True,
        )
        for leave in self.sudo():
            event = leave.calendar_event_id.with_env(Event.env)
            if leave.state not in CALENDAR_STATES or not (leave.date_from and leave.date_to):
                if event:
                    leave.calendar_event_id = False
                    event.unlink()
                continue
            values = leave._calendar_event_values()
            if event.exists():
                event.write(values)
            else:
                leave.calendar_event_id = Event.create(values)

    # ------------------------------------------------------------------
    # Visibility of the leave events (security/rostering_calendar_security.xml)
    # ------------------------------------------------------------------
    @api.model
    def _calendar_visible_ids(self):
        """The requests the logged-in user can see in Rostering, whatever
        environment (even sudo) the calendar rule is evaluated in."""
        user = self.env.user
        Leave = self.with_user(user).sudo(False).with_context(active_test=False)
        if not Leave.has_access('read'):
            return []
        return Leave.search([]).ids

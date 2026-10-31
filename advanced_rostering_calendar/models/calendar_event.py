# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.advanced_rostering.models.rostering_tools import search_positive

# What a leave event takes from its leave request: changing these in Calendar
# is refused (Calendar's own bookkeeping, e.g. attendees' answers, still works).
LEAVE_EVENT_FIELDS = {
    'name', 'start', 'stop', 'start_date', 'stop_date', 'allday', 'duration', 'partner_ids', 'user_id',
    'description', 'privacy', 'show_as', 'res_model_id', 'res_id', 'recurrency',
}


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    rostering_leave_visible = fields.Boolean(
        string='Leave Request Visible', compute='_compute_rostering_leave_visible',
        search='_search_rostering_leave_visible',
        help='Whether the current user can see the leave request of this event in Rostering.',
    )

    @api.depends_context('uid')
    def _compute_rostering_leave_visible(self):
        visible = set(self.env['rostering.leave']._calendar_visible_ids())
        for event in self:
            event.rostering_leave_visible = event.res_model == 'rostering.leave' and event.res_id in visible

    def _search_rostering_leave_visible(self, operator, value):
        positive = search_positive(operator, value)
        if positive is None:
            return NotImplemented
        domain = [('res_model', '=', 'rostering.leave'),
                  ('res_id', 'in', self.env['rostering.leave']._calendar_visible_ids())]
        return domain if positive else ['!', '&'] + domain

    def _is_rostering_leave_event(self):
        return any(event.res_model == 'rostering.leave' for event in self)

    def _skip_send_mail_status_update(self):
        # Leave events never send invitations or cancellations.
        if self._is_rostering_leave_event():
            return True
        return super()._skip_send_mail_status_update()

    def write(self, vals):
        if (not self.env.context.get('rostering_calendar_sync') and self._is_rostering_leave_event()
                and LEAVE_EVENT_FIELDS & set(vals)):
            raise UserError(_('This event shows a leave request. Change the leave request in Rostering '
                              'and the calendar follows.'))
        return super().write(vals)

    @api.ondelete(at_uninstall=True)
    def _unlink_except_rostering_leave(self):
        if not self.env.context.get('rostering_calendar_sync') and self._is_rostering_leave_event():
            raise UserError(_('This event shows a leave request. Cancel or delete the leave request in '
                              'Rostering and the calendar follows.'))

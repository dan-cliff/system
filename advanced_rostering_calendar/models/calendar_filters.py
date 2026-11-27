# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CalendarFilters(models.Model):
    _inherit = 'calendar.filters'

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **read_kwargs):
        # The Calendar app loads the user's calendars here: offer the shared
        # Leave Requests calendar once to everyone with Rostering.
        self._rostering_offer_leave_calendar()
        return super().search_read(domain, fields, offset=offset, limit=limit, order=order, **read_kwargs)

    @api.model
    def _rostering_offer_leave_calendar(self):
        user = self.env.user
        if user.share or user.sudo().rostering_leave_calendar_offered:
            return
        if not user.has_group('advanced_rostering.group_rostering_user'):
            return
        partner = self.env.ref('advanced_rostering_calendar.partner_leave_requests_calendar',
                               raise_if_not_found=False)
        if not partner:
            return
        Filter = self.sudo()
        if not Filter.search_count([('user_id', '=', user.id), ('partner_id', '=', partner.id)]):
            Filter.create({'user_id': user.id, 'partner_id': partner.id, 'partner_checked': True})
        # Offered once: a user who removes the calendar keeps it removed.
        user.sudo().rostering_leave_calendar_offered = True


class ResUsers(models.Model):
    _inherit = 'res.users'

    rostering_leave_calendar_offered = fields.Boolean(
        string='Leave Requests Calendar Offered', copy=False,
        help='The shared Leave Requests calendar was added to this user\'s Calendar once.',
    )

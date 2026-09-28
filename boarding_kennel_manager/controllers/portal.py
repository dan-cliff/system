from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class KennelPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'kennel_resident_count' in counters:
            Resident = request.env['kennel.resident']
            values['kennel_resident_count'] = (
                Resident.search_count([]) if Resident.has_access('read') else 0)
        if 'kennel_booking_count' in counters:
            Booking = request.env['kennel.booking']
            values['kennel_booking_count'] = (
                Booking.search_count([]) if Booking.has_access('read') else 0)
        return values

    def _kennel_care_log(self, domain, limit=50):
        """Completed tasks (with the photos from their history entry), newest first."""
        return request.env['kennel.task'].sudo().search(
            domain + [('state', '=', 'done')], order='done_datetime desc, id desc', limit=limit)

    # ------------------------------------------------------------------
    # Animals
    # ------------------------------------------------------------------

    @http.route(['/my/kennel/animals', '/my/kennel/animals/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_kennel_animals(self, page=1, **kw):
        Resident = request.env['kennel.resident']
        count = Resident.search_count([])
        pager = portal_pager(url='/my/kennel/animals', total=count, page=page, step=self._items_per_page)
        residents = Resident.search([], order='name', limit=self._items_per_page, offset=pager['offset'])
        request.session['my_kennel_animals_history'] = residents.ids[:100]
        values = self._prepare_portal_layout_values()
        values.update({
            'residents': residents.sudo(),
            'page_name': 'kennel_animals',
            'pager': pager,
            'default_url': '/my/kennel/animals',
        })
        return request.render('boarding_kennel_manager.portal_my_kennel_animals', values)

    @http.route(['/my/kennel/animals/<int:resident_id>'], type='http', auth='public', website=True)
    def portal_my_kennel_animal(self, resident_id, access_token=None, **kw):
        try:
            resident_sudo = self._document_check_access('kennel.resident', resident_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        values = self._prepare_portal_layout_values()
        values.update({
            'resident': resident_sudo,
            'page_name': 'kennel_animal',
            'stays': resident_sudo.booking_line_ids.sorted(lambda line: line.arrival_datetime, reverse=True),
            'care_log': self._kennel_care_log([('resident_id', '=', resident_sudo.id)]),
        })
        values = self._get_page_view_values(
            resident_sudo, access_token or resident_sudo._portal_ensure_token(), values,
            'my_kennel_animals_history', False, **kw)
        return request.render('boarding_kennel_manager.portal_my_kennel_animal', values)

    # ------------------------------------------------------------------
    # Bookings
    # ------------------------------------------------------------------

    @http.route(['/my/kennel/bookings', '/my/kennel/bookings/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_kennel_bookings(self, page=1, **kw):
        Booking = request.env['kennel.booking']
        count = Booking.search_count([])
        pager = portal_pager(url='/my/kennel/bookings', total=count, page=page, step=self._items_per_page)
        bookings = Booking.search([], limit=self._items_per_page, offset=pager['offset'])
        request.session['my_kennel_bookings_history'] = bookings.ids[:100]
        values = self._prepare_portal_layout_values()
        values.update({
            'bookings': bookings.sudo(),
            'page_name': 'kennel_bookings',
            'pager': pager,
            'default_url': '/my/kennel/bookings',
        })
        return request.render('boarding_kennel_manager.portal_my_kennel_bookings', values)

    @http.route(['/my/kennel/bookings/<int:booking_id>'], type='http', auth='public', website=True)
    def portal_my_kennel_booking(self, booking_id, access_token=None, **kw):
        try:
            booking_sudo = self._document_check_access('kennel.booking', booking_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        values = self._prepare_portal_layout_values()
        values.update({
            'booking': booking_sudo,
            'page_name': 'kennel_booking',
            'care_log': self._kennel_care_log([('booking_id', '=', booking_sudo.id)]),
        })
        values = self._get_page_view_values(
            booking_sudo, access_token or booking_sudo._portal_ensure_token(), values,
            'my_kennel_bookings_history', False, **kw)
        return request.render('boarding_kennel_manager.portal_my_kennel_booking', values)

"""Signing in and out from the Odoo toolbar (systray)."""
from odoo import http
from odoo.http import request

SYSTRAY_GROUP = 'advanced_attendance.group_onsite_systray'


def _systray_employee():
    """The current user's employee in the active company, if they may use the toolbar button."""
    user = request.env.user
    if not user.has_group(SYSTRAY_GROUP):
        return None
    employee = user.employee_id
    if not employee or not employee.sudo().company_id.onsite_systray:
        return None
    return employee


def _where(latitude=False, longitude=False):
    """Location details recorded when the company tracks them."""
    try:
        geoip = request.geoip
        city = geoip.city.name if geoip.city else ''
        country = geoip.country_name or ''
        ip = geoip.ip
        latitude = latitude or geoip.location.latitude or False
        longitude = longitude or geoip.location.longitude or False
    except Exception:  # noqa: BLE001 - GeoIP database not installed
        city = country = ''
        ip = request.httprequest.remote_addr
    return {
        'latitude': latitude or 0.0,
        'longitude': longitude or 0.0,
        'location': ', '.join(part for part in (city, country) if part),
        'ip_address': ip,
        'browser': request.httprequest.user_agent.browser or '',
    }


class OnSiteSystray(http.Controller):

    @http.route('/advanced_attendance/systray_data', type='jsonrpc', auth='user', readonly=True)
    def systray_data(self):
        employee = _systray_employee()
        return employee._onsite_systray_data() if employee else {}

    @http.route('/advanced_attendance/systray_sign_in_out', type='jsonrpc', auth='user')
    def systray_sign_in_out(self, latitude=False, longitude=False):
        employee = _systray_employee()
        if not employee:
            return {}
        company = employee.sudo().company_id
        where = _where(latitude, longitude) if company.onsite_location_tracking else None
        employee._onsite_sign_in_out(where)
        return employee._onsite_systray_data()

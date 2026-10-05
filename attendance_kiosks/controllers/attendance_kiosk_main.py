"""Attendance kiosk - token based, login free PWA.

Routes (``<token>`` is the kiosk's access token, which makes each URL unique):
    GET  /kiosk/<token>                      Kiosk app
    GET  /kiosk/<token>/manifest.webmanifest PWA manifest
    GET  /kiosk/<token>/sw.js                Service worker (offline)
    GET  /kiosk/<token>/config.json          Kiosk settings and questionnaires
    GET  /kiosk/<token>/roster.json          Workers, eligibility and sign in state
    GET  /kiosk/<token>/avatar/<employee>    Worker photo
    POST /kiosk/<token>/identify             Badge or name (+ PIN) identification
    POST /kiosk/<token>/action               Sign in / sign out
    POST /kiosk/<token>/sync                 Replay events recorded offline
"""
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from odoo import _, fields, http
from odoo.http import request
from odoo.tools import consteq, file_open

_logger = logging.getLogger(__name__)

# PIN brute force protection (per worker process): 5 wrong PINs in 5 minutes
# locks the worker out of that kiosk for the rest of the window.
PIN_ATTEMPTS = 5
PIN_WINDOW_SECONDS = 5 * 60
_failed_pins = defaultdict(list)

# Offline events are trusted, but never further back than this.
MAX_OFFLINE_AGE = timedelta(days=14)


def _json(data, status=200, cache='no-store'):
    return request.make_response(
        json.dumps(data),
        headers=[('Content-Type', 'application/json'), ('Cache-Control', cache)],
        status=status,
    )


def _error(message, status=400, **extra):
    return _json({'status': 'error', 'message': message, **extra}, status=status)


def _get_kiosk(token):
    if not token or len(token) < 16:
        return None
    return request.env['attendance.kiosk'].sudo().search([('access_token', '=', token)], limit=1) or None


def _body():
    try:
        data = json.loads(request.httprequest.get_data(as_text=True) or '{}')
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _parse_time(value):
    """ISO 8601 UTC string from the kiosk -> naive UTC datetime, clamped to now."""
    now = fields.Datetime.now()
    if not value:
        return now
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return now
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    parsed = parsed.replace(microsecond=0)
    return min(parsed, now)


def _pin_locked(kiosk, employee_id):
    key = (kiosk.id, employee_id)
    cutoff = time.time() - PIN_WINDOW_SECONDS
    _failed_pins[key] = [t for t in _failed_pins[key] if t > cutoff]
    return len(_failed_pins[key]) >= PIN_ATTEMPTS


def _pin_failed(kiosk, employee_id):
    _failed_pins[(kiosk.id, employee_id)].append(time.time())


class AttendanceKioskController(http.Controller):

    # ── App shell ──────────────────────────────────────────────────────────
    @http.route('/kiosk/<string:token>', type='http', auth='public', methods=['GET'], csrf=False, save_session=False)
    def kiosk_app(self, token, **kw):
        kiosk = _get_kiosk(token)
        if not kiosk:
            return request.make_response(
                _('This kiosk link is not valid. Ask your administrator for the current link.'),
                headers=[('Content-Type', 'text/plain; charset=utf-8')], status=404,
            )
        response = request.render('attendance_kiosks.kiosk_app', {'kiosk': kiosk, 'token': token})
        response.headers['Cache-Control'] = 'no-cache'
        return response

    @http.route('/kiosk/<string:token>/manifest.webmanifest', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def kiosk_manifest(self, token, **kw):
        kiosk = _get_kiosk(token)
        if not kiosk:
            return _json({}, status=404)
        icon = '/attendance_kiosks/static/src/img/icon-%s.png'
        manifest = {
            'id': f'/kiosk/{token}',
            'name': f'{kiosk.name} - Sign In',
            'short_name': kiosk.name[:12],
            'description': _('Sign in kiosk for %(location)s, %(company)s',
                             location=kiosk.work_location_id.name, company=kiosk.company_id.name),
            'start_url': f'/kiosk/{token}',
            'scope': f'/kiosk/{token}',
            'display': 'standalone',
            'display_override': ['fullscreen', 'standalone'],
            'orientation': 'any',
            'background_color': '#0f172a',
            'theme_color': '#0f172a',
            'icons': [
                {'src': icon % 192, 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
                {'src': icon % 512, 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
                {'src': icon % 'maskable-512', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
            ],
        }
        return request.make_response(
            json.dumps(manifest),
            headers=[('Content-Type', 'application/manifest+json'), ('Cache-Control', 'no-cache')],
        )

    @http.route('/kiosk/<string:token>/sw.js', type='http', auth='public', methods=['GET'], csrf=False,
                save_session=False)
    def kiosk_service_worker(self, token, **kw):
        kiosk = _get_kiosk(token)
        if not kiosk:
            return request.make_response('', status=404)
        with file_open('attendance_kiosks/static/src/kiosk/kiosk_sw.js') as f:
            script = f.read()
        script = script.replace('__KIOSK_SCOPE__', f'/kiosk/{token}')
        return request.make_response(script, headers=[
            ('Content-Type', 'application/javascript'),
            ('Service-Worker-Allowed', f'/kiosk/{token}'),
            ('Cache-Control', 'no-cache, no-store, must-revalidate'),
        ])

    # ── Data ───────────────────────────────────────────────────────────────
    @http.route('/kiosk/<string:token>/config.json', type='http', auth='public', methods=['GET'], csrf=False,
                save_session=False)
    def kiosk_config(self, token, **kw):
        kiosk = _get_kiosk(token)
        if not kiosk:
            return _error(_('Kiosk not found.'), status=404)
        return _json(kiosk._kiosk_config())

    @http.route('/kiosk/<string:token>/roster.json', type='http', auth='public', methods=['GET'], csrf=False,
                save_session=False)
    def kiosk_roster(self, token, **kw):
        kiosk = _get_kiosk(token)
        if not kiosk:
            return _error(_('Kiosk not found.'), status=404)
        kiosk.last_contact = fields.Datetime.now()
        employees = kiosk._kiosk_base_employees()
        return _json({
            'server_time': fields.Datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'employees': kiosk._kiosk_employee_payloads(employees),
        })

    @http.route('/kiosk/<string:token>/avatar/<int:employee_id>', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def kiosk_avatar(self, token, employee_id, **kw):
        kiosk = _get_kiosk(token)
        if not kiosk:
            return request.make_response('', status=404)
        employee = request.env['hr.employee'].sudo().browse(employee_id).exists()
        if not employee or not kiosk._kiosk_filter_ids(kiosk._kiosk_base_domain(), employee):
            return request.make_response('', status=404)
        return request.env['ir.binary']._get_image_stream_from(
            employee, 'avatar_128',
        ).get_response(max_age=86400)

    # ── Identification ─────────────────────────────────────────────────────
    @http.route('/kiosk/<string:token>/identify', type='http', auth='public', methods=['POST'], csrf=False,
                save_session=False)
    def kiosk_identify(self, token, **kw):
        kiosk = _get_kiosk(token)
        if not kiosk:
            return _error(_('Kiosk not found.'), status=404)
        data = _body()
        if data is None:
            return _error(_('Invalid request.'))
        Employee = request.env['hr.employee'].sudo()
        method = data.get('method')
        if method == 'badge' and kiosk.identify_badge:
            badge = str(data.get('badge') or '').strip()
            employee = badge and Employee.search([('barcode', '=', badge)], limit=1)
            if not employee:
                return _error(_('Badge not recognised.'), status=404)
        elif method == 'name' and kiosk.identify_name:
            try:
                employee = Employee.browse(int(data.get('employee_id'))).exists()
            except (TypeError, ValueError):
                employee = Employee
            if not employee or not kiosk._kiosk_filter_ids(kiosk._kiosk_base_domain(), employee):
                return _error(_('You are not permitted to sign in at this kiosk.'), status=403)
            if kiosk.require_pin:
                if not employee.pin:
                    return _error(_('You do not have a PIN yet. Please see your supervisor.'), status=403)
                if _pin_locked(kiosk, employee.id):
                    return _error(_('Too many wrong PINs. Please wait a few minutes and try again.'), status=429)
                if not consteq(str(data.get('pin') or ''), employee.pin):
                    _pin_failed(kiosk, employee.id)
                    return _error(_('Wrong PIN. Please try again.'), status=403, code='bad_pin')
        else:
            return _error(_('This way of signing in is not available at this kiosk.'), status=403)

        payload = kiosk._kiosk_employee_payloads(employee)[0]
        payload.pop('badge', None)
        payload.pop('pin', None)
        return _json({
            'status': 'ok',
            'employee': payload,
            'due': kiosk._kiosk_questionnaires_due(employee, fields.Datetime.now()).ids,
            'ticket': kiosk._kiosk_make_ticket(employee),
        })

    # ── Sign in / sign out ─────────────────────────────────────────────────
    @http.route('/kiosk/<string:token>/action', type='http', auth='public', methods=['POST'], csrf=False,
                save_session=False)
    def kiosk_action(self, token, **kw):
        kiosk = _get_kiosk(token)
        if not kiosk:
            return _error(_('Kiosk not found.'), status=404)
        data = _body()
        if data is None:
            return _error(_('Invalid request.'))
        try:
            employee_id = int(data.get('employee_id'))
        except (TypeError, ValueError):
            return _error(_('Invalid request.'))
        if not kiosk._kiosk_check_ticket(data.get('ticket'), employee_id):
            return _error(_('Please identify yourself again.'), status=401, code='ticket')
        employee = request.env['hr.employee'].sudo().browse(employee_id).exists()
        if not employee:
            return _error(_('Employee not found.'), status=404)
        now = fields.Datetime.now()
        action = data.get('action')
        if action == 'sign_in':
            result = kiosk._kiosk_sign_in(employee, now, data.get('answers') or [])
        elif action == 'sign_out':
            result = kiosk._kiosk_sign_out(employee, now)
        else:
            return _error(_('Invalid request.'))
        payload = kiosk._kiosk_employee_payloads(employee)[0]
        payload.pop('badge', None)
        payload.pop('pin', None)
        result['employee'] = payload
        return _json(result)

    # ── Offline sync ───────────────────────────────────────────────────────
    @http.route('/kiosk/<string:token>/sync', type='http', auth='public', methods=['POST'], csrf=False,
                save_session=False)
    def kiosk_sync(self, token, **kw):
        kiosk = _get_kiosk(token)
        if not kiosk:
            return _error(_('Kiosk not found.'), status=404)
        if not kiosk.offline_enabled:
            return _error(_('Offline use is turned off for this kiosk.'), status=403)
        data = _body()
        if data is None or not isinstance(data.get('events'), list):
            return _error(_('Invalid request.'))
        kiosk.last_contact = fields.Datetime.now()
        Employee = request.env['hr.employee'].sudo()
        oldest = fields.Datetime.now() - MAX_OFFLINE_AGE
        results, failures = [], []
        for event in sorted(data['events'], key=lambda e: str(e.get('time') or '')):
            event_id = str(event.get('id') or '')[:64]
            try:
                employee = Employee.browse(int(event.get('employee_id'))).exists()
            except (TypeError, ValueError):
                employee = Employee
            when = _parse_time(event.get('time'))
            if not event_id or not employee or event.get('action') not in ('sign_in', 'sign_out'):
                results.append({'id': event_id, 'status': 'error', 'message': 'invalid event'})
                continue
            if when < oldest:
                result = {'status': 'error', 'message': _('Too old to sync.')}
            else:
                try:
                    with request.env.cr.savepoint():
                        if event['action'] == 'sign_in':
                            result = kiosk._kiosk_sign_in(
                                employee, when, event.get('answers') or [], offline=True, event=event_id)
                        else:
                            result = kiosk._kiosk_sign_out(employee, when, offline=True, event=event_id)
                except Exception as error:  # noqa: BLE001 - report and keep syncing the rest
                    _logger.warning('Kiosk %s could not sync event %s: %s', kiosk.id, event_id, error)
                    result = {'status': 'error', 'message': str(error)}
            if result.get('status') == 'error':
                failures.append(_(
                    '%(action)s for %(employee)s at %(time)s: %(error)s',
                    action=_('Sign in') if event['action'] == 'sign_in' else _('Sign out'),
                    employee=employee.name, time=kiosk._kiosk_format_datetime(when),
                    error=result.get('message'),
                ))
            results.append({'id': event_id, **{k: v for k, v in result.items() if k in ('status', 'message')}})
        if failures:
            kiosk.message_post(body=_(
                'Some sign ins or sign outs recorded offline could not be synced and need checking: %s',
                '; '.join(failures),
            ))
        return _json({'status': 'ok', 'results': results})

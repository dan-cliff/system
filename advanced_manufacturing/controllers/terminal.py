# -*- coding: utf-8 -*-
"""Work Centre app - token based, login free PWA (one per work centre).

Routes (``<token>`` is the work centre's token, which makes each URL unique):
    GET  /manufacturing/workcentre/<token>                      The app
    GET  /manufacturing/workcentre/<token>/manifest.webmanifest PWA manifest
    GET  /manufacturing/workcentre/<token>/sw.js                Service worker (offline)
    GET  /manufacturing/workcentre/<token>/config.json          Settings
    GET  /manufacturing/workcentre/<token>/data.json            Workers and work orders
    GET  /manufacturing/workcentre/<token>/avatar/<employee>    Worker photo
    POST /manufacturing/workcentre/<token>/identify             Badge or name (+ PIN)
    POST /manufacturing/workcentre/<token>/action               Record work (online)
    POST /manufacturing/workcentre/<token>/sync                 Replay work recorded offline

Workers identify the same ways as at On Site's sign in kiosks (badge camera,
external RFID / barcode reader, name and PIN), as chosen in Manufacturing's
Settings. Online, identification returns a signed ticket the app sends with
each action. Offline, the app checks badges and PINs against its hashed copy
and queues what workers do; /sync applies it in order, each event once.
"""
import hashlib
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from odoo import _, fields, http
from odoo.http import request
from odoo.tools import consteq, file_open

_logger = logging.getLogger(__name__)

PREFIX = '/manufacturing/workcentre'
STATIC = 'advanced_manufacturing/static/src/terminal/'

# PIN brute force protection (per worker process): 5 wrong PINs in 5 minutes
# locks the worker out of that work centre for the rest of the window.
PIN_ATTEMPTS = 5
PIN_WINDOW_SECONDS = 5 * 60
_failed_pins = defaultdict(list)

# Offline events are trusted, but never further back than this.
MAX_OFFLINE_AGE = timedelta(days=14)


@lru_cache(maxsize=1)
def _asset_version():
    """Fingerprint of the app's script and stylesheet, so devices fetch them again
    whenever they change."""
    digest = hashlib.sha256()
    for name in ('terminal.js', 'terminal.css'):
        with file_open(STATIC + name, 'rb') as f:
            digest.update(f.read())
    return digest.hexdigest()[:12]


def _json(data, status=200):
    return request.make_response(
        json.dumps(data),
        headers=[('Content-Type', 'application/json'), ('Cache-Control', 'no-store')],
        status=status,
    )


def _error(message, status=400, **extra):
    return _json({'status': 'error', 'message': message, **extra}, status=status)


def _get_workcenter(token):
    if not token or len(token) < 16:
        return None
    return request.env['mrp.workcenter'].sudo().search(
        [('terminal_token', '=', token), ('active', '=', True)], limit=1) or None


def _body():
    try:
        data = json.loads(request.httprequest.get_data(as_text=True) or '{}')
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _parse_time(value):
    """ISO 8601 UTC string from the app -> naive UTC datetime, clamped to now."""
    now = fields.Datetime.now()
    if not value:
        return now
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return now
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return min(parsed.replace(microsecond=0), now)


def _pin_locked(workcenter, employee_id):
    key = (workcenter.id, employee_id)
    cutoff = time.time() - PIN_WINDOW_SECONDS
    _failed_pins[key] = [t for t in _failed_pins[key] if t > cutoff]
    return len(_failed_pins[key]) >= PIN_ATTEMPTS


def _pin_failed(workcenter, employee_id):
    _failed_pins[(workcenter.id, employee_id)].append(time.time())


def _workcenter_env(workcenter):
    """The work centre in its own company, so records it creates land there."""
    company = workcenter.company_id or request.env.company
    return workcenter.with_company(company).with_context(allowed_company_ids=[company.id])


class WorkCentreTerminal(http.Controller):

    # ── App shell ──────────────────────────────────────────────────────────
    @http.route(PREFIX + '/<string:token>', type='http', auth='public', methods=['GET'], csrf=False,
                save_session=False)
    def terminal_app(self, token, **kw):
        workcenter = _get_workcenter(token)
        if not workcenter:
            return request.make_response(
                _('This Work Centre link is not valid. Ask your administrator for the current link.'),
                headers=[('Content-Type', 'text/plain; charset=utf-8')], status=404,
            )
        response = request.render('advanced_manufacturing.terminal_app', {
            'workcenter': workcenter, 'token': token, 'asset_version': _asset_version(),
        })
        response.headers['Cache-Control'] = 'no-cache'
        return response

    @http.route(PREFIX + '/<string:token>/manifest.webmanifest', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def terminal_manifest(self, token, **kw):
        workcenter = _get_workcenter(token)
        if not workcenter:
            return _json({}, status=404)
        icon = '/advanced_manufacturing/static/src/img/icon-%s.png'
        scope = f'{PREFIX}/{token}'
        manifest = {
            'id': scope,
            'name': f'{workcenter.name} - Work Centre',
            'short_name': workcenter.name[:12],
            'description': _('Work Centre app for %(workcenter)s, %(company)s',
                             workcenter=workcenter.name, company=workcenter._terminal_company().name),
            'start_url': scope,
            'scope': scope,
            'display': 'standalone',
            'display_override': ['fullscreen', 'standalone'],
            'orientation': 'any',
            'background_color': '#1e2a5e',
            'theme_color': '#1e2a5e',
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

    @http.route(PREFIX + '/<string:token>/sw.js', type='http', auth='public', methods=['GET'], csrf=False,
                save_session=False)
    def terminal_service_worker(self, token, **kw):
        if not _get_workcenter(token):
            return request.make_response('', status=404)
        with file_open(STATIC + 'terminal_sw.js') as f:
            script = f.read()
        scope = f'{PREFIX}/{token}'
        script = script.replace('__SCOPE__', scope).replace('__ASSET_VERSION__', _asset_version())
        return request.make_response(script, headers=[
            ('Content-Type', 'application/javascript'),
            ('Service-Worker-Allowed', scope),
            ('Cache-Control', 'no-cache, no-store, must-revalidate'),
        ])

    # ── Data ───────────────────────────────────────────────────────────────
    @http.route(PREFIX + '/<string:token>/config.json', type='http', auth='public', methods=['GET'], csrf=False,
                save_session=False)
    def terminal_config(self, token, **kw):
        workcenter = _get_workcenter(token)
        if not workcenter:
            return _error(_('Work centre not found.'), status=404)
        return _json(_workcenter_env(workcenter)._terminal_config())

    @http.route(PREFIX + '/<string:token>/data.json', type='http', auth='public', methods=['GET'], csrf=False,
                save_session=False)
    def terminal_data(self, token, **kw):
        workcenter = _get_workcenter(token)
        if not workcenter:
            return _error(_('Work centre not found.'), status=404)
        workcenter.terminal_last_contact = fields.Datetime.now()
        return _json(_workcenter_env(workcenter)._terminal_data())

    @http.route(PREFIX + '/<string:token>/avatar/<int:employee_id>', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def terminal_avatar(self, token, employee_id, **kw):
        workcenter = _get_workcenter(token)
        if not workcenter:
            return request.make_response('', status=404)
        employee = request.env['hr.employee'].sudo().browse(employee_id).exists()
        if not employee or not workcenter._terminal_can_use(employee):
            return request.make_response('', status=404)
        return request.env['ir.binary']._get_image_stream_from(employee, 'avatar_128').get_response(max_age=86400)

    # ── Identification ─────────────────────────────────────────────────────
    @http.route(PREFIX + '/<string:token>/identify', type='http', auth='public', methods=['POST'], csrf=False,
                save_session=False)
    def terminal_identify(self, token, **kw):
        workcenter = _get_workcenter(token)
        if not workcenter:
            return _error(_('Work centre not found.'), status=404)
        data = _body()
        if data is None:
            return _error(_('Invalid request.'))
        workcenter = _workcenter_env(workcenter)
        company = workcenter._terminal_company()
        Employee = request.env['hr.employee'].sudo()
        method = data.get('method')
        if (method == 'badge' and company.mrp_terminal_identify_badge) or \
                (method == 'reader' and company.mrp_terminal_identify_reader):
            scanned = str(data.get('badge') or '')[:128]
            employee = workcenter._terminal_find_badge(scanned)
            if not employee:
                _logger.info('Work centre %s: no employee has the Badge ID %r (%s)', workcenter.id, scanned, method)
                return _error(_('Badge not recognised.'), status=404, scanned=scanned)
        elif method == 'name' and company.mrp_terminal_identify_name:
            try:
                employee = Employee.browse(int(data.get('employee_id'))).exists()
            except (TypeError, ValueError):
                employee = Employee
            if not employee or not workcenter._terminal_can_use(employee):
                return _error(_('You are not permitted to work at this work centre.'), status=403)
            if company.mrp_terminal_require_pin:
                if not employee.pin:
                    return _error(_('You do not have a PIN yet. Please see your supervisor.'), status=403)
                if _pin_locked(workcenter, employee.id):
                    return _error(_('Too many wrong PINs. Please wait a few minutes and try again.'), status=429)
                if not consteq(str(data.get('pin') or ''), employee.pin):
                    _pin_failed(workcenter, employee.id)
                    return _error(_('Wrong PIN. Please try again.'), status=403, code='bad_pin')
        else:
            return _error(_('This way of signing in is not available at this work centre.'), status=403)

        payload = workcenter._terminal_employee_payloads(employee)[0]
        payload.pop('badge', None)
        payload.pop('pin', None)
        if payload['refusals']:
            return _error(' '.join(payload['refusals']), status=403, employee=payload)
        workcenter.sudo().terminal_last_contact = fields.Datetime.now()
        return _json({'status': 'ok', 'employee': payload, 'ticket': workcenter._terminal_make_ticket(employee)})

    # ── Recording work ─────────────────────────────────────────────────────
    @http.route(PREFIX + '/<string:token>/action', type='http', auth='public', methods=['POST'], csrf=False,
                save_session=False)
    def terminal_action(self, token, **kw):
        workcenter = _get_workcenter(token)
        if not workcenter:
            return _error(_('Work centre not found.'), status=404)
        data = _body()
        if data is None or not isinstance(data.get('event'), dict):
            return _error(_('Invalid request.'))
        try:
            employee_id = int(data.get('employee_id'))
        except (TypeError, ValueError):
            return _error(_('Invalid request.'))
        workcenter = _workcenter_env(workcenter)
        if not workcenter._terminal_check_ticket(data.get('ticket'), employee_id):
            return _error(_('Please sign in again.'), status=401, code='ticket')
        employee = request.env['hr.employee'].sudo().browse(employee_id).exists()
        if not employee or not workcenter._terminal_can_use(employee):
            return _error(_('You are not permitted to work at this work centre.'), status=403)
        refusals = workcenter._terminal_refusals(employee)[employee.id]
        if refusals:
            return _error(' '.join(refusals), status=403)
        result = workcenter._terminal_apply(data['event'], employee, fields.Datetime.now())
        workcenter.sudo().terminal_last_contact = fields.Datetime.now()
        result['data'] = workcenter._terminal_data()
        return _json(result)

    @http.route(PREFIX + '/<string:token>/sync', type='http', auth='public', methods=['POST'], csrf=False,
                save_session=False)
    def terminal_sync(self, token, **kw):
        workcenter = _get_workcenter(token)
        if not workcenter:
            return _error(_('Work centre not found.'), status=404)
        workcenter = _workcenter_env(workcenter)
        if not workcenter._terminal_company().mrp_terminal_offline:
            return _error(_('Offline use is turned off.'), status=403)
        data = _body()
        if data is None or not isinstance(data.get('events'), list):
            return _error(_('Invalid request.'))
        workcenter.sudo().terminal_last_contact = fields.Datetime.now()
        Employee = request.env['hr.employee'].sudo()
        oldest = fields.Datetime.now() - MAX_OFFLINE_AGE
        results = []
        # Events arrive in the order the workers recorded them.
        for event in data['events'][:500]:
            if not isinstance(event, dict):
                continue
            event_id = str(event.get('id') or '')[:64]
            try:
                employee = Employee.browse(int(event.get('employee_id'))).exists()
            except (TypeError, ValueError):
                employee = Employee
            if not event_id or not employee or not workcenter._terminal_can_use(employee):
                results.append({'id': event_id, 'status': 'error', 'message': 'invalid event'})
                continue
            when = _parse_time(event.get('time'))
            if when < oldest:
                result = {'status': 'error', 'message': _('Too old to sync.')}
            else:
                try:
                    result = workcenter._terminal_apply(event, employee, when, offline=True)
                except Exception as error:  # noqa: BLE001 - report it and keep syncing the rest
                    _logger.warning('Work centre %s could not sync event %s: %s', workcenter.id, event_id, error)
                    result = {'status': 'error', 'message': str(error)}
            results.append({'id': event_id, 'status': result['status'], 'message': result.get('message', '')})
        return _json({'status': 'ok', 'results': results, 'data': workcenter._terminal_data()})

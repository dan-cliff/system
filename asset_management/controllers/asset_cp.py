# -*- coding: utf-8 -*-
"""
Asset Control Plane — token-based, login-free web interface.

Routes:
    GET  /asset/cp/<token>                  Landing page
    GET  /asset/cp/<token>/usage/new        Usage reading form
    POST /asset/cp/<token>/usage/new        Submit usage reading
    GET  /asset/cp/<token>/defect/new       Defect report form
    POST /asset/cp/<token>/defect/new       Submit defect report
    GET  /asset/cp/<token>/maintenance/new  Maintenance log form
    POST /asset/cp/<token>/maintenance/new  Submit maintenance log
    GET  /asset/cp/<token>/users.json       Active internal users list (for offline cache)
    GET  /asset/cp/<token>/manifest.json    PWA Web App Manifest
    GET  /asset/cp/<token>/sw.js            Service Worker (offline)
    POST /asset/cp/<token>/sync             Offline batch-sync endpoint
"""
import json
import logging
import urllib.request
from datetime import date

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _parse_cp_date(date_str):
    """Parse a date string in DD/MM/YYYY or YYYY-MM-DD format into YYYY-MM-DD."""
    if not date_str:
        return str(date.today())
    date_str = date_str.strip()
    # DD/MM/YYYY
    try:
        from datetime import datetime
        return datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
    except ValueError:
        pass
    # Already YYYY-MM-DD
    try:
        from datetime import datetime
        datetime.strptime(date_str, '%Y-%m-%d')
        return date_str
    except ValueError:
        pass
    return str(date.today())


def _reverse_geocode(lat, lon):
    """Return a human-readable address for the given coordinates via OSM Nominatim."""
    try:
        url = (
            f'https://nominatim.openstreetmap.org/reverse'
            f'?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=0'
        )
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'OdooAssetManagement/1.0 (asset_management module)'},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
            return data.get('display_name', '')
    except Exception as e:
        _logger.warning('Reverse geocode failed for (%s, %s): %s', lat, lon, e)
        return ''


def _get_asset(token):
    """Resolve a control-plane token to an asset record (sudo)."""
    if not token:
        return None
    return request.env['asset.asset'].sudo().search([('cp_token', '=', token)], limit=1)


def _employee_identity(employee):
    """Return a JSON-serialisable identity dict for an employee."""
    avatar = ''
    if employee.image_128:
        avatar = 'data:image/png;base64,' + employee.image_128.decode()
    return {
        'status': 'ok',
        'employee_id': employee.id,
        'employee_name': employee.name,
        'user_id': employee.user_id.id if employee.user_id else None,
        'avatar': avatar,
    }


def _cp_error(token, message):
    return request.render('asset_management.cp_error', {
        'message': message,
        'token': token,
    })


class AssetControlPlane(http.Controller):

    # ── PWA Manifest ──────────────────────────────────────────────────────
    @http.route('/asset/cp/<string:token>/manifest.json', auth='public', type='http', methods=['GET'], csrf=False)
    def cp_manifest(self, token, **kw):
        asset = _get_asset(token)
        if not asset:
            return request.make_response('{}', headers=[('Content-Type', 'application/json')], status=404)

        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        manifest = {
            'name': asset.name,
            'short_name': asset.asset_number or asset.name[:12],
            'description': f'Control Plane for {asset.name}',
            'start_url': f'/asset/cp/{token}',
            'scope': f'/asset/cp/{token}',
            'location_tracking': asset.eff_location_tracking,
            'display': 'standalone',
            'background_color': '#1a1a2e',
            'theme_color': '#0d6efd',
            'orientation': 'portrait',
            'icons': [
                {
                    'src': f'{base_url}/asset_management/static/src/img/icon-192.png',
                    'sizes': '192x192',
                    'type': 'image/png',
                    'purpose': 'any maskable',
                },
                {
                    'src': f'{base_url}/asset_management/static/src/img/icon-512.png',
                    'sizes': '512x512',
                    'type': 'image/png',
                    'purpose': 'any maskable',
                },
            ],
        }
        return request.make_response(
            json.dumps(manifest, indent=2),
            headers=[
                ('Content-Type', 'application/manifest+json'),
                ('Cache-Control', 'no-cache'),
            ],
        )

    # ── Service Worker ────────────────────────────────────────────────────
    @http.route('/asset/cp/<string:token>/sw.js', auth='public', type='http', methods=['GET'], csrf=False)
    def cp_service_worker(self, token, **kw):
        """Serve the service worker scoped to this asset's control plane."""
        asset = _get_asset(token)
        if not asset:
            return request.make_response('', status=404)

        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        location_tracking = asset.eff_location_tracking
        sw_js = f"""
// Asset Control Plane Service Worker — {asset.name}
// Scope: /asset/cp/{token}/

const CACHE_NAME        = 'asset-cp-{token[:8]}-v2';
const SYNC_TAG          = 'asset-cp-sync-{token[:8]}';
const LOC_SYNC_TAG      = 'asset-cp-loc-{token[:8]}';
const PERIODIC_LOC_TAG  = 'asset-cp-periodic-{token[:8]}';
const DB_NAME           = 'asset-cp-{token[:8]}';
const DB_VERSION        = 2;
const LOCATION_ENABLED  = {'true' if location_tracking else 'false'};

const URLS_TO_CACHE = [
  '/asset/cp/{token}',
  '/asset/cp/{token}/usage/new',
  '/asset/cp/{token}/defect/new',
  '/asset/cp/{token}/maintenance/new',
  '/asset/cp/{token}/users.json',
  '{base_url}/asset_management/static/src/css/cp.css',
];

// ── Install: cache shell ───────────────────────────────────────────────────
self.addEventListener('install', (event) => {{
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(URLS_TO_CACHE)).catch(() => {{}})
  );
}});

// ── Activate: clean old caches ────────────────────────────────────────────
self.addEventListener('activate', (event) => {{
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
}});

// ── Fetch: network-first for POST, cache-first for GET ───────────────────
self.addEventListener('fetch', (event) => {{
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;
  if (url.pathname.startsWith('/asset/cp/{token}/sync')) return;
  if (url.pathname.startsWith('/asset/cp/{token}/location')) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {{
        if (response && response.status === 200 && response.type === 'basic') {{
          const cloned = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, cloned));
        }}
        return response;
      }})
      .catch(() => caches.match(event.request).then((cached) => cached || offlinePage()))
  );
}});

// ── Background Sync ───────────────────────────────────────────────────────
self.addEventListener('sync', (event) => {{
  if (event.tag === SYNC_TAG) {{
    event.waitUntil(flushPendingSubmissions());
  }}
  if (event.tag === LOC_SYNC_TAG && LOCATION_ENABLED) {{
    event.waitUntil(flushPendingLocation());
  }}
}});

// ── Periodic Background Sync (Chrome/Android, installed PWA) ─────────────
self.addEventListener('periodicsync', (event) => {{
  if (event.tag === PERIODIC_LOC_TAG && LOCATION_ENABLED) {{
    event.waitUntil(flushPendingLocation());
  }}
}});

// ── Flush queued form submissions ─────────────────────────────────────────
async function flushPendingSubmissions() {{
  const db = await openDB();
  const items = await getAllPending(db);
  const results = await Promise.allSettled(
    items.map((item) =>
      fetch('/asset/cp/{token}/sync', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json', 'X-CP-Token': '{token}' }},
        body: JSON.stringify(item.data),
      }})
      .then((r) => {{ if (r.ok) deletePending(db, item.id); }})
    )
  );
  return results;
}}

// ── Flush last-known location to server ───────────────────────────────────
async function flushPendingLocation() {{
  try {{
    const db = await openDB();
    const loc = await getLastLocation(db);
    if (!loc || !loc.latitude) return;
    const res = await fetch('/asset/cp/{token}/location', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(loc),
    }});
    if (res.ok) await clearLastLocation(db);
  }} catch (_) {{}}
}}

// ── IndexedDB helpers ─────────────────────────────────────────────────────
function openDB() {{
  return new Promise((resolve, reject) => {{
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {{
      const db = e.target.result;
      if (!db.objectStoreNames.contains('pending')) {{
        db.createObjectStore('pending', {{ keyPath: 'id', autoIncrement: true }});
      }}
      if (!db.objectStoreNames.contains('last_location')) {{
        db.createObjectStore('last_location', {{ keyPath: 'id' }});
      }}
    }};
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = (e) => reject(e.target.error);
  }});
}}

function getAllPending(db) {{
  return new Promise((resolve) => {{
    const tx = db.transaction('pending', 'readonly');
    const req = tx.objectStore('pending').getAll();
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = () => resolve([]);
  }});
}}

function deletePending(db, id) {{
  return new Promise((resolve) => {{
    const tx = db.transaction('pending', 'readwrite');
    tx.objectStore('pending').delete(id);
    tx.oncomplete = resolve;
  }});
}}

function getLastLocation(db) {{
  return new Promise((resolve) => {{
    const tx = db.transaction('last_location', 'readonly');
    const req = tx.objectStore('last_location').get('current');
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = () => resolve(null);
  }});
}}

function clearLastLocation(db) {{
  return new Promise((resolve) => {{
    const tx = db.transaction('last_location', 'readwrite');
    tx.objectStore('last_location').delete('current');
    tx.oncomplete = resolve;
  }});
}}

function offlinePage() {{
  return new Response(
    '<html><body style="font-family:sans-serif;text-align:center;padding:2rem"><h2>You are offline</h2><p>Your entry has been saved and will sync automatically when you reconnect.</p></body></html>',
    {{ headers: {{ 'Content-Type': 'text/html' }} }}
  );
}}
"""
        return request.make_response(
            sw_js,
            headers=[
                ('Content-Type', 'application/javascript'),
                ('Service-Worker-Allowed', f'/asset/cp/{token}/'),
                ('Cache-Control', 'no-cache, no-store, must-revalidate'),
            ],
        )

    # ── Barcode Identity Auth ─────────────────────────────────────────────
    @http.route('/asset/cp/<string:token>/auth/barcode', auth='public', type='http', methods=['POST'], csrf=False)
    def cp_auth_barcode(self, token, **kw):
        """Verify an employee ID-card barcode and return the employee identity."""
        asset = _get_asset(token)
        if not asset:
            return request.make_response(
                json.dumps({'status': 'error', 'message': 'Asset not found'}),
                headers=[('Content-Type', 'application/json')],
                status=404,
            )
        try:
            body = request.httprequest.get_data(as_text=True)
            data = json.loads(body) if body else {}
        except Exception:
            return request.make_response(
                json.dumps({'status': 'error', 'message': 'Invalid JSON'}),
                headers=[('Content-Type', 'application/json')],
                status=400,
            )
        barcode = (data.get('barcode') or '').strip()
        if not barcode:
            return request.make_response(
                json.dumps({'status': 'error', 'message': 'Barcode is required'}),
                headers=[('Content-Type', 'application/json')],
                status=400,
            )
        employee = request.env['hr.employee'].sudo().search(
            [('barcode', '=', barcode)], limit=1
        )
        if not employee:
            return request.make_response(
                json.dumps({'status': 'error', 'message': 'Employee not found. Please check your ID card.'}),
                headers=[('Content-Type', 'application/json')],
                status=404,
            )
        return request.make_response(
            json.dumps(_employee_identity(employee)),
            headers=[('Content-Type', 'application/json')],
        )

    # ── PIN Identity Auth ─────────────────────────────────────────────────
    @http.route('/asset/cp/<string:token>/auth/pin', auth='public', type='http', methods=['POST'], csrf=False)
    def cp_auth_pin(self, token, **kw):
        """Verify an employee PIN code and return the employee identity."""
        asset = _get_asset(token)
        if not asset:
            return request.make_response(
                json.dumps({'status': 'error', 'message': 'Asset not found'}),
                headers=[('Content-Type', 'application/json')],
                status=404,
            )
        try:
            body = request.httprequest.get_data(as_text=True)
            data = json.loads(body) if body else {}
        except Exception:
            return request.make_response(
                json.dumps({'status': 'error', 'message': 'Invalid JSON'}),
                headers=[('Content-Type', 'application/json')],
                status=400,
            )
        pin = (data.get('pin') or '').strip()
        if not pin:
            return request.make_response(
                json.dumps({'status': 'error', 'message': 'PIN is required'}),
                headers=[('Content-Type', 'application/json')],
                status=400,
            )
        employee = request.env['hr.employee'].sudo().search(
            [('pin', '=', pin)], limit=1
        )
        if not employee:
            return request.make_response(
                json.dumps({'status': 'error', 'message': 'PIN not recognised. Please try again.'}),
                headers=[('Content-Type', 'application/json')],
                status=404,
            )
        return request.make_response(
            json.dumps(_employee_identity(employee)),
            headers=[('Content-Type', 'application/json')],
        )

    # ── Users List (for offline defect reporter select) ───────────────────
    @http.route('/asset/cp/<string:token>/users.json', auth='public', type='http', methods=['GET'], csrf=False)
    def cp_users_json(self, token, **kw):
        """Return active internal users as JSON so the service worker can cache them."""
        asset = _get_asset(token)
        if not asset:
            return request.make_response(
                json.dumps([]),
                headers=[('Content-Type', 'application/json')],
                status=404,
            )
        users = request.env['res.users'].sudo().search(
            [('active', '=', True), ('share', '=', False)],
            order='name asc',
        )
        payload = [{'id': u.id, 'name': u.name} for u in users]
        return request.make_response(
            json.dumps(payload),
            headers=[
                ('Content-Type', 'application/json'),
                ('Cache-Control', 'no-cache'),
            ],
        )

    # ── Landing Page ──────────────────────────────────────────────────────
    @http.route('/asset/cp/<string:token>', auth='public', type='http', methods=['GET'], website=False, csrf=False)
    def cp_landing(self, token, **kw):
        asset = _get_asset(token)
        if not asset:
            return _cp_error(token, 'Asset not found. Please check the link.')

        recent_usage = asset.usage_log_ids.sorted(
            key=lambda r: (r.date or date.min, r.id), reverse=True
        )[:5]
        recent_defects = asset.defect_ids.filtered(
            lambda d: d.state in ('open', 'in_progress')
        ).sorted('date', reverse=True)[:5]
        recent_maintenance = asset.maintenance_log_ids.sorted('date', reverse=True)[:3]

        return request.render('asset_management.cp_landing', {
            'asset': asset,
            'token': token,
            'recent_usage': recent_usage,
            'recent_defects': recent_defects,
            'recent_maintenance': recent_maintenance,
        })

    # ── Usage Reading ─────────────────────────────────────────────────────
    @http.route('/asset/cp/<string:token>/usage/new', auth='public', type='http', methods=['GET'], website=False, csrf=False)
    def cp_usage_form(self, token, success=None, **kw):
        asset = _get_asset(token)
        if not asset:
            return _cp_error(token, 'Asset not found.')
        if not asset.eff_usage_tracking:
            return _cp_error(token, 'Usage tracking is not enabled for this asset.')
        users = request.env['res.users'].sudo().search(
            [('active', '=', True), ('share', '=', False)], order='name asc'
        )
        return request.render('asset_management.cp_usage_form', {
            'asset': asset,
            'token': token,
            'success': success == '1',
            'today': date.today().strftime('%d/%m/%Y'),
            'users': users,
        })

    @http.route('/asset/cp/<string:token>/usage/new', auth='public', type='http', methods=['POST'], website=False, csrf=False)
    def cp_usage_submit(self, token, **post):
        asset = _get_asset(token)
        if not asset:
            return _cp_error(token, 'Asset not found.')
        try:
            reading = float(post.get('reading', 0) or 0)
            entry_date = _parse_cp_date(post.get('date', ''))
            notes = post.get('notes', '').strip()
            raw_uid = post.get('user_id', '').strip()
            user_id = request.env.ref('base.public_user').id
            if raw_uid and raw_uid.isdigit():
                u = request.env['res.users'].sudo().browse(int(raw_uid))
                if u.exists():
                    user_id = u.id

            request.env['asset.usage.log'].sudo().create({
                'asset_id': asset.id,
                'date': entry_date,
                'reading': reading,
                'notes': notes,
                'user_id': user_id,
                'source': 'control_plane',
            })
        except Exception as e:
            _logger.warning('CP usage submit error: %s', e)
            return _cp_error(token, 'Failed to save usage reading. Please try again.')

        return request.redirect(f'/asset/cp/{token}/usage/new?success=1')

    # ── Defect Report ─────────────────────────────────────────────────────
    @http.route('/asset/cp/<string:token>/defect/new', auth='public', type='http', methods=['GET'], website=False, csrf=False)
    def cp_defect_form(self, token, success=None, **kw):
        asset = _get_asset(token)
        if not asset:
            return _cp_error(token, 'Asset not found.')
        users = request.env['res.users'].sudo().search(
            [('active', '=', True), ('share', '=', False)],
            order='name asc',
        )
        severities = request.env['asset.defect.severity'].sudo().search([], order='sequence, name')
        return request.render('asset_management.cp_defect_form', {
            'asset': asset,
            'token': token,
            'success': success == '1',
            'today': date.today().strftime('%d/%m/%Y'),
            'users': users,
            'severities': severities,
        })

    @http.route('/asset/cp/<string:token>/defect/new', auth='public', type='http', methods=['POST'], website=False, csrf=False)
    def cp_defect_submit(self, token, **post):
        asset = _get_asset(token)
        if not asset:
            return _cp_error(token, 'Asset not found.')
        try:
            sev_name = post.get('severity', '').strip()
            sev = request.env['asset.defect.severity'].sudo().search(
                [('name', '=ilike', sev_name)], limit=1
            ) if sev_name else request.env['asset.defect.severity'].sudo().browse()
            vals = {
                'asset_id': asset.id,
                'date': _parse_cp_date(post.get('date', '')),
                'description': post.get('description', '').strip(),
                'severity_id': sev.id if sev else False,
                'source': 'control_plane',
            }
            raw_uid = post.get('user_id', '').strip()
            if raw_uid and raw_uid.isdigit():
                user = request.env['res.users'].sudo().browse(int(raw_uid))
                if user.exists():
                    vals['reported_by'] = user.id
                    vals['reported_by_name'] = user.name
            else:
                vals['reported_by_name'] = post.get('reporter_name', '').strip()
            request.env['asset.defect'].sudo().create(vals)
        except Exception as e:
            _logger.warning('CP defect submit error: %s', e)
            return _cp_error(token, 'Failed to save defect report. Please try again.')

        return request.redirect(f'/asset/cp/{token}/defect/new?success=1')

    # ── Maintenance Log ───────────────────────────────────────────────────
    @http.route('/asset/cp/<string:token>/maintenance/new', auth='public', type='http', methods=['GET'], website=False, csrf=False)
    def cp_maintenance_form(self, token, success=None, **kw):
        asset = _get_asset(token)
        if not asset:
            return _cp_error(token, 'Asset not found.')
        if not asset.eff_maintenance:
            return _cp_error(token, 'Maintenance tracking is not enabled for this asset.')
        users = request.env['res.users'].sudo().search(
            [('active', '=', True), ('share', '=', False)], order='name asc'
        )
        maintenance_types = request.env['asset.maintenance.type'].sudo().search([], order='name asc')
        return request.render('asset_management.cp_maintenance_form', {
            'asset': asset,
            'token': token,
            'success': success == '1',
            'today': date.today().strftime('%d/%m/%Y'),
            'users': users,
            'maintenance_types': maintenance_types,
        })

    @http.route('/asset/cp/<string:token>/maintenance/new', auth='public', type='http', methods=['POST'], website=False, csrf=False)
    def cp_maintenance_submit(self, token, **post):
        asset = _get_asset(token)
        if not asset:
            return _cp_error(token, 'Asset not found.')
        try:
            maint_type_name = post.get('maintenance_type', '').strip()
            maint_type = request.env['asset.maintenance.type'].sudo().search(
                [('name', '=ilike', maint_type_name)], limit=1
            ) if maint_type_name else request.env['asset.maintenance.type'].sudo().browse()
            maint_vals = {
                'asset_id': asset.id,
                'date': _parse_cp_date(post.get('date', '')),
                'maintenance_type_id': maint_type.id if maint_type else False,
                'description': post.get('description', '').strip(),
                'parts_used': post.get('parts_used', '').strip(),
                'next_due_date': _parse_cp_date(post.get('next_due_date', '')) if post.get('next_due_date') else False,
                'source': 'control_plane',
            }
            raw_uid = post.get('user_id', '').strip()
            if raw_uid and raw_uid.isdigit():
                u = request.env['res.users'].sudo().browse(int(raw_uid))
                if u.exists():
                    maint_vals['performed_by'] = u.id
                    maint_vals['performed_by_name'] = u.name
            else:
                maint_vals['performed_by_name'] = post.get('technician_name', '').strip()
            request.env['asset.maintenance.log'].sudo().create(maint_vals)
        except Exception as e:
            _logger.warning('CP maintenance submit error: %s', e)
            return _cp_error(token, 'Failed to save maintenance log. Please try again.')

        return request.redirect(f'/asset/cp/{token}/maintenance/new?success=1')

    # ── Location Update ───────────────────────────────────────────────────
    @http.route('/asset/cp/<string:token>/location', auth='public', type='http', methods=['POST'], website=False, csrf=False)
    def cp_location_update(self, token, **kw):
        """Receive a GPS location update from the Control Plane PWA."""
        asset = _get_asset(token)
        if not asset:
            return request.make_response(
                json.dumps({'status': 'error', 'message': 'Asset not found'}),
                headers=[('Content-Type', 'application/json')],
                status=404,
            )
        if not asset.eff_location_tracking:
            return request.make_response(
                json.dumps({'status': 'error', 'message': 'Location tracking not enabled'}),
                headers=[('Content-Type', 'application/json')],
                status=403,
            )
        try:
            body = request.httprequest.get_data(as_text=True)
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        try:
            lat = float(data.get('latitude', 0))
            lon = float(data.get('longitude', 0))
            accuracy = float(data.get('accuracy', 0))
            if lat == 0 and lon == 0:
                raise ValueError('Invalid coordinates')

            from datetime import datetime
            address = _reverse_geocode(lat, lon)
            asset.sudo().write({
                'latitude': lat,
                'longitude': lon,
                'location_accuracy': accuracy,
                'location_updated': datetime.utcnow(),
                'nearest_address': address,
            })
            request.env['asset.location.log'].sudo().create({
                'asset_id': asset.id,
                'latitude': lat,
                'longitude': lon,
                'accuracy': accuracy,
                'nearest_address': address,
                'source': 'control_plane',
            })
        except Exception as e:
            _logger.warning('CP location update error: %s', e)
            return request.make_response(
                json.dumps({'status': 'error', 'message': str(e)}),
                headers=[('Content-Type', 'application/json')],
                status=400,
            )

        return request.make_response(
            json.dumps({'status': 'ok'}),
            headers=[('Content-Type', 'application/json')],
        )

    # ── Offline Batch Sync Endpoint ───────────────────────────────────────
    @http.route('/asset/cp/<string:token>/sync', auth='public', type='http', methods=['POST'], website=False, csrf=False)
    def cp_sync(self, token, **kw):
        """Receives a batch of offline-queued submissions from the service worker."""
        asset = _get_asset(token)
        if not asset:
            return request.make_response(
                json.dumps({'status': 'error', 'message': 'Asset not found'}),
                headers=[('Content-Type', 'application/json')],
                status=404,
            )

        try:
            body = request.httprequest.get_data(as_text=True)
            payload = json.loads(body) if body else {}
        except Exception:
            return request.make_response(
                json.dumps({'status': 'error', 'message': 'Invalid JSON'}),
                headers=[('Content-Type', 'application/json')],
                status=400,
            )

        record_type = payload.get('type')
        data = payload.get('data', {})
        created_id = None

        try:
            if record_type == 'usage':
                raw_uid = str(data.get('user_id', '')).strip()
                user_id = request.env.ref('base.public_user').id
                if raw_uid and raw_uid.isdigit():
                    u = request.env['res.users'].sudo().browse(int(raw_uid))
                    if u.exists():
                        user_id = u.id
                rec = request.env['asset.usage.log'].sudo().create({
                    'asset_id': asset.id,
                    'date': _parse_cp_date(data.get('date', '')),
                    'reading': float(data.get('reading', 0) or 0),
                    'notes': data.get('notes', ''),
                    'user_id': user_id,
                    'source': 'control_plane',
                })
                created_id = rec.id

            elif record_type == 'defect':
                sync_sev_name = str(data.get('severity', '')).strip()
                sync_sev = request.env['asset.defect.severity'].sudo().search(
                    [('name', '=ilike', sync_sev_name)], limit=1
                ) if sync_sev_name else request.env['asset.defect.severity'].sudo().browse()
                defect_vals = {
                    'asset_id': asset.id,
                    'date': _parse_cp_date(data.get('date', '')),
                    'description': data.get('description', ''),
                    'severity_id': sync_sev.id if sync_sev else False,
                    'source': 'control_plane',
                }
                raw_uid = str(data.get('user_id', '')).strip()
                if raw_uid and raw_uid.isdigit():
                    user = request.env['res.users'].sudo().browse(int(raw_uid))
                    if user.exists():
                        defect_vals['reported_by'] = user.id
                        defect_vals['reported_by_name'] = user.name
                else:
                    defect_vals['reported_by_name'] = data.get('reporter_name', '')
                rec = request.env['asset.defect'].sudo().create(defect_vals)
                created_id = rec.id

            elif record_type == 'maintenance':
                sync_type_name = str(data.get('maintenance_type', '')).strip()
                sync_maint_type = request.env['asset.maintenance.type'].sudo().search(
                    [('name', '=ilike', sync_type_name)], limit=1
                ) if sync_type_name else request.env['asset.maintenance.type'].sudo().browse()
                sync_maint_vals = {
                    'asset_id': asset.id,
                    'date': _parse_cp_date(data.get('date', '')),
                    'maintenance_type_id': sync_maint_type.id if sync_maint_type else False,
                    'description': data.get('description', ''),
                    'parts_used': data.get('parts_used', ''),
                    'next_due_date': _parse_cp_date(data.get('next_due_date', '')) if data.get('next_due_date') else False,
                    'source': 'control_plane',
                }
                raw_uid = str(data.get('user_id', '')).strip()
                if raw_uid and raw_uid.isdigit():
                    u = request.env['res.users'].sudo().browse(int(raw_uid))
                    if u.exists():
                        sync_maint_vals['performed_by'] = u.id
                        sync_maint_vals['performed_by_name'] = u.name
                else:
                    sync_maint_vals['performed_by_name'] = data.get('technician_name', '')
                rec = request.env['asset.maintenance.log'].sudo().create(sync_maint_vals)
                created_id = rec.id

            else:
                return request.make_response(
                    json.dumps({'status': 'error', 'message': f'Unknown record type: {record_type}'}),
                    headers=[('Content-Type', 'application/json')],
                    status=400,
                )

        except Exception as e:
            _logger.warning('CP sync error for asset %s: %s', asset.id, e)
            return request.make_response(
                json.dumps({'status': 'error', 'message': str(e)}),
                headers=[('Content-Type', 'application/json')],
                status=500,
            )

        return request.make_response(
            json.dumps({'status': 'ok', 'id': created_id}),
            headers=[('Content-Type', 'application/json')],
        )

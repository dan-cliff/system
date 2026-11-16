#!/usr/bin/env python3
"""Video Room Display: the program a room's PC runs (an IoT Interfaces Node).

Started and kept running (and updated over the air) by the IoT Node agent. It
reaches Odoo only through the agent's local address ($IOT_PROXY_URL), which signs
every request: this program holds no key.

Every second during a call (a few seconds when idle) it:
  1. syncs with Odoo: sends the room's state, gets the room's settings and the
     commands from the Room Console;
  2. arranges the screens (xrandr) and Chrome's windows when the layout changes;
  3. carries out the commands: joining and leaving calls, mic, camera, sharing,
     layout, volume, TV power, camera presets, identify screens;
  4. reads the meeting page's state through the platform driver.

Chrome runs in the kiosk session (room_browser.sh) with DevTools on 127.0.0.1 only;
the platform drivers (drivers/*.js) are injected into the meeting page from here.
"""
import hashlib
import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp  # noqa: E402
import devices  # noqa: E402

VERSION = '1.0.0'
PROXY = os.environ.get('IOT_PROXY_URL', 'http://127.0.0.1:8099').rstrip('/')
PROGRAM_DIR = os.environ.get('IOT_PROGRAM_DIR') or os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('IOT_DATA_DIR') or os.path.join(PROGRAM_DIR, 'data')
IDLE_URL = PROXY + '/video_rooms/node/v1/display'
SHARE_URL = PROXY + '/video_rooms/node/v1/share-window'
SHARE_TITLE = 'Video Rooms Share'
WORLD = 'videoRooms'
JOIN_TIMEOUT = 10 * 60
STEP_EVERY = 2

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
_logger = logging.getLogger('video_rooms')


def odoo(path, payload):
    request = urllib.request.Request(PROXY + path, data=json.dumps(payload).encode(), method='POST',
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode() or '{}')


def load_config():
    try:
        with open(os.path.join(DATA_DIR, 'config.json')) as file:
            return json.load(file)
    except (OSError, ValueError):
        return {}


def driver_bundle(platform):
    """The JavaScript injected into a meeting page for ``platform``."""
    folder = os.path.join(PROGRAM_DIR, 'drivers')
    with open(os.path.join(folder, 'selectors.json')) as file:
        selectors = json.load(file).get(platform, {})
    parts = []
    for name in ['driver_base.js'] + sorted(f for f in os.listdir(folder) if f.endswith('.js') and f != 'driver_base.js'):
        with open(os.path.join(folder, name)) as file:
            parts.append(file.read())
    parts.append('window.__vrMake(%s, %s, (window.__vrHooks || {})[%s] || {});'
                 % (json.dumps(platform), json.dumps(selectors), json.dumps(platform)))
    return '\n;\n'.join(parts)


MODIFIERS = {'Alt': 1, 'Control': 2, 'Ctrl': 2, 'Meta': 4, 'Shift': 8}


class PageDriver:
    """A meeting page with its platform driver injected (isolated world)."""

    def __init__(self, target):
        self.session = cdp.connect_page(target)
        self.target_id = target['id']
        self.context_id = None
        self.main_frame = None
        self.script_id = None
        self.platform = None
        self.session.on('Runtime.executionContextCreated', self._context_created)
        self.session.on('Runtime.executionContextsCleared', lambda _p: setattr(self, 'context_id', None))
        self.session.on('Runtime.bindingCalled', self._binding)
        self.session.call('Page.enable')
        self.session.call('Runtime.enable')
        self.main_frame = self.session.call('Page.getFrameTree')['frameTree']['frame']['id']
        self.session.call('Runtime.addBinding', {'name': 'vrNative', 'executionContextName': WORLD})

    def _context_created(self, params):
        context = params.get('context') or {}
        aux = context.get('auxData') or {}
        if context.get('name') == WORLD and aux.get('frameId') == self.main_frame:
            self.context_id = context['id']

    def _binding(self, params):
        # Runs on the DevTools reader thread, which must stay free to receive the answers
        # to the clicks and keys sent below: do them on a thread of their own.
        if params.get('name') == 'vrNative':
            threading.Thread(target=self._native, args=(params,), daemon=True).start()

    def _native(self, params):
        try:
            data = json.loads(params.get('payload') or '{}')
            if data.get('op') == 'click':
                self.click(data['x'], data['y'])
            elif data.get('op') == 'keys':
                self.keys(data['combo'])
        except (ValueError, KeyError, cdp.CdpError) as error:
            _logger.warning('Driver request failed: %s', error)

    def use_platform(self, platform):
        """Inject ``platform``'s driver now and into every page this window loads."""
        if self.script_id:
            try:
                self.session.call('Page.removeScriptToEvaluateOnNewDocument', {'identifier': self.script_id})
            except cdp.CdpError:
                pass
        self.platform = platform
        self.script_id = self.session.call('Page.addScriptToEvaluateOnNewDocument', {
            'source': driver_bundle(platform), 'worldName': WORLD, 'runImmediately': True})['identifier']

    def navigate(self, url):
        self.context_id = None
        self.session.call('Page.navigate', {'url': url})

    def call(self, method, *args, timeout=15):
        """window.__vr.<method>(*args) in the driver's world; None until the page is ready."""
        if not self.context_id:
            return None
        expression = 'window.__vr ? window.__vr.%s(%s) : null' % (method, ', '.join(json.dumps(a) for a in args))
        try:
            result = self.session.call('Runtime.evaluate', {
                'expression': expression, 'contextId': self.context_id, 'returnByValue': True,
                'awaitPromise': True}, timeout=timeout)
        except cdp.CdpError as error:
            _logger.debug('Driver call %s failed: %s', method, error)
            return None
        if result.get('exceptionDetails'):
            _logger.warning('Driver %s.%s: %s', self.platform, method,
                            result['exceptionDetails'].get('exception', {}).get('description', '')[:300])
            return None
        return (result.get('result') or {}).get('value')

    def click(self, x, y):
        for kind in ('mouseMoved', 'mousePressed', 'mouseReleased'):
            self.session.call('Input.dispatchMouseEvent', {'type': kind, 'x': x, 'y': y, 'button': 'left',
                                                           'clickCount': 1})

    def keys(self, combo):
        parts = combo.split('+')
        key = parts[-1]
        modifiers = sum(MODIFIERS.get(p, 0) for p in parts[:-1])
        code = ('Key%s' % key.upper()) if len(key) == 1 and key.isalpha() else key
        vk = ord(key.upper()) if len(key) == 1 else 0
        for kind in ('rawKeyDown', 'keyUp'):
            self.session.call('Input.dispatchKeyEvent', {'type': kind, 'modifiers': modifiers, 'key': key,
                                                         'code': code, 'windowsVirtualKeyCode': vk})

    def close(self):
        self.session.close()


class Browser:
    """The room's Chrome: windows placed on the screens."""

    def __init__(self):
        self.session = None
        self.windows = {}  # role -> {'target': id, 'driver': PageDriver|None}

    def ready(self):
        if self.session and self.session.alive:
            return True
        if not cdp.browser_available():
            return False
        self.session = cdp.connect_browser()
        self.windows = {}
        # Adopt the window room_browser.sh opened as the call window; close any others.
        pages = cdp.page_targets()
        for index, page in enumerate(pages):
            if index == 0:
                self.windows['call'] = {'target': page['id'], 'driver': None}
            else:
                self.session.call('Target.closeTarget', {'targetId': page['id']})
        return True

    def window(self, role, url, rect=None, offscreen=False):
        """Open (or reuse) the window for ``role`` and place it."""
        info = self.windows.get(role)
        if info:
            try:
                self.session.call('Target.activateTarget', {'targetId': info['target']})
            except cdp.CdpError:
                info = None
        if not info:
            target = self.session.call('Target.createTarget', {'url': url, 'newWindow': True})['targetId']
            info = self.windows[role] = {'target': target, 'driver': None}
        self.place(role, rect, offscreen)
        return info

    def place(self, role, rect, offscreen=False):
        info = self.windows.get(role)
        if not info:
            return
        try:
            window_id = self.session.call('Browser.getWindowForTarget', {'targetId': info['target']})['windowId']
            self.session.call('Browser.setWindowBounds', {'windowId': window_id, 'bounds': {'windowState': 'normal'}})
            if offscreen:
                bounds = {'left': 20000, 'top': 0, 'width': 1920, 'height': 1080}
            elif rect:
                bounds = {'left': rect[0], 'top': rect[1], 'width': rect[2], 'height': rect[3]}
            else:
                bounds = {'windowState': 'fullscreen'}
            self.session.call('Browser.setWindowBounds', {'windowId': window_id, 'bounds': bounds})
        except cdp.CdpError as error:
            _logger.warning('Placing the %s window failed: %s', role, error)

    def driver(self, role):
        info = self.windows.get(role)
        if not info:
            return None
        if not info['driver'] or not info['driver'].session.alive:
            target = next((t for t in cdp.page_targets() if t['id'] == info['target']), None)
            if not target:
                self.windows.pop(role, None)
                return None
            info['driver'] = PageDriver(target)
        return info['driver']

    def close(self, role):
        info = self.windows.pop(role, None)
        if info:
            if info['driver']:
                info['driver'].close()
            try:
                self.session.call('Target.closeTarget', {'targetId': info['target']})
            except cdp.CdpError:
                pass

    def restart(self):
        try:
            self.session.call('Browser.close')
        except cdp.CdpError:
            pass
        self.session = None


class RoomDisplay:

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.browser = Browser()
        self.config = load_config()
        self.room = {}
        self.layout_key = None
        self.groups = []
        self.rects = {}
        self.results = []
        self.call = None        # {'call_id', 'params', 'started', 'state', 'last_step'}
        self.companion = False
        self.state = {'call_state': 'idle', 'volume': devices.get_volume(), 'version': VERSION}
        self.ha_read_at = 0
        self.ha_published = None

    # ── Loop ─────────────────────────────────────────────────────────────
    def run(self):
        _logger.info('Video Room Display %s starting', VERSION)
        while True:
            poll = 5
            try:
                poll = self.tick()
            except (urllib.error.URLError, OSError, ValueError) as error:
                _logger.warning('Odoo unreachable: %s', error)
            except Exception:
                _logger.exception('Unexpected error')
            time.sleep(poll)

    def tick(self):
        self.refresh_state()
        available = devices.outputs()
        answer = odoo('/video_rooms/node/v1/sync', {
            'state': self.state, 'results': self.results,
            'outputs': [name for name, info in available.items() if info['connected']],
        })
        self.results = []
        self.room = answer.get('room') or {}
        if not self.call and self.state.get('call_state') in ('ended', 'error'):
            # Odoo has now heard how the last call ended.
            self.state.update(call_state='idle', call_id=None, mic=None, camera=None, sharing=False, error='')
        if not self.browser.ready():
            return 3
        self.apply_layout()
        for command in answer.get('commands') or []:
            self.results.append(self.handle(command))
        self.advance_call()
        self.home_assistant_sync()
        return answer.get('poll') or 3

    # ── Screens and windows ──────────────────────────────────────────────
    def apply_layout(self):
        screens = self.room.get('screens') or []
        key = hashlib.sha256(json.dumps([screens, sorted(devices.outputs())], sort_keys=True).encode()).hexdigest()
        if key == self.layout_key:
            return
        self.layout_key = key
        if screens:
            self.groups, self.rects = devices.apply_layout(screens)
        else:
            self.groups, self.rects = [{'content': 'call', 'screens': [], 'rect': None}], {}
        call_group = next((g for g in self.groups if g['content'] == 'call'), None)
        self.browser.window('call', IDLE_URL, call_group['rect'] if call_group else None)
        for index, group in enumerate(g for g in self.groups if g['content'] == 'info'):
            self.browser.window('info%s' % index, IDLE_URL, group['rect'])
        _logger.info('Screens arranged: %s', [(g['content'], g['rect']) for g in self.groups])

    def shared_group(self):
        return next((g for g in self.groups if g['content'] == 'shared'), None)

    # ── Commands ─────────────────────────────────────────────────────────
    def handle(self, command):
        name = command.get('command')
        params = command.get('params') or {}
        try:
            message = getattr(self, 'do_%s' % name)(params) if hasattr(self, 'do_%s' % name) else None
            if message is None and not hasattr(self, 'do_%s' % name):
                raise RuntimeError('This Room Display doesn\'t know "%s" yet: update its program.' % name)
            return {'id': command['id'], 'ok': True, 'message': message or ''}
        except Exception as error:  # report every failure to Odoo
            _logger.warning('Command %s failed: %s', name, error)
            return {'id': command['id'], 'ok': False, 'message': str(error)[:240]}

    def do_join(self, params):
        if self.call:
            self.end_call(navigate=False)
        driver = self.browser.driver('call')
        if not driver:
            self.browser.window('call', IDLE_URL)
            driver = self.browser.driver('call')
        driver.use_platform(params['driver'])
        driver.navigate(params['url'])
        self.call = {'call_id': params.get('call_id'), 'params': params, 'started': time.time(),
                     'state': 'prejoin', 'last_step': 0, 'error': ''}
        self.state.update(call_id=params.get('call_id'), call_state='prejoin', error='')
        return 'Joining'

    def do_leave(self, params):
        driver = self.browser.driver('call')
        if driver and self.call:
            driver.call('leave')
            time.sleep(1.5)
        self.end_call()
        return 'Left the call'

    def end_call(self, navigate=True):
        self.browser.close('companion')
        self.browser.close('share')
        self.companion = False
        if navigate:
            driver = self.browser.driver('call')
            if driver:
                driver.navigate(IDLE_URL)
        if self.call:
            self.state.update(call_state='ended')
        self.call = None

    def _in_call_driver(self):
        driver = self.browser.driver('call')
        if not driver or not self.call:
            raise RuntimeError('The room isn\'t in a call.')
        return driver

    def do_mic(self, params):
        self._in_call_driver().call('setMic', bool(params.get('value')))

    def do_camera(self, params):
        self._in_call_driver().call('setCamera', bool(params.get('value')))

    def do_layout(self, params):
        self._in_call_driver().call('setLayout', params.get('value') or 'gallery')

    def do_share(self, params):
        """Share the HDMI capture or a wireless share: into the call when there is one
        (the window is kept off-screen and the platform shares it), otherwise shown on the
        room's screens for an in-room presentation."""
        value = params.get('value')
        driver = self.browser.driver('call') if self.call else None
        if value == 'stop':
            if driver:
                driver.call('stopShare')
            self.browser.close('share')
            return 'Stopped sharing'
        mode = 'wireless' if value == 'wireless' else 'hdmi'
        capture = devices.hdmi_capture(self.config)
        if mode == 'hdmi' and not capture:
            raise RuntimeError('No HDMI capture card found on the room PC.')
        url = '%s?mode=%s&device=%s&session=%s' % (SHARE_URL, mode, urllib.parse.quote(capture or ''),
                                                 urllib.parse.quote(params.get('session') or ''))
        self.browser.close('share')
        if driver:
            self.browser.window('share', url, offscreen=True)
            time.sleep(2)  # let the picture start before the platform looks for the window
            driver.call('startShare', SHARE_TITLE)
            return 'Sharing into the call'
        call_group = next((g for g in self.groups if g['content'] == 'call'), None)
        self.browser.window('share', url, call_group['rect'] if call_group else None)
        return "Showing on the room's screens"

    def do_volume(self, params):
        self.state['volume'] = devices.set_volume(params.get('value', 60))

    def do_tv_power(self, params):
        devices.tv_power(bool(params.get('value')), self.room.get('tv_control'), self.room.get('screens') or [])

    def do_identify(self, params):
        seconds = int(params.get('seconds') or 8)
        shown = []
        for screen in self.room.get('screens') or []:
            rect = self.rects.get(screen['id'])
            if not rect:
                continue
            page = ('data:text/html,<body style="margin:0;background:%%23000;color:%%23FFC93C;display:grid;'
                    'place-items:center;height:100vh;font:700 40vh system-ui">%s</body>' % screen['number'])
            role = 'identify%s' % screen['id']
            self.browser.window(role, page, rect)
            shown.append(role)
        threading.Timer(seconds, lambda: [self.browser.close(r) for r in shown]).start()
        return 'Showing %s screen numbers' % len(shown)

    def do_restart_browser(self, params):
        self.end_call(navigate=False)
        self.browser.restart()
        self.layout_key = None

    def do_ptz_preset(self, params):
        devices.ptz_recall(params.get('value'), self.config, DATA_DIR)

    def do_device(self, params):
        kind = params.get('kind')
        if kind == 'ptz':
            devices.ptz_recall(params.get('value'), self.config, DATA_DIR)
        elif kind == 'ptz_save':
            devices.ptz_save(params.get('value'), self.config, DATA_DIR)
        elif kind == 'ha':
            return self.home_assistant(params)
        elif kind == 'ha_discover':
            template = '{%% set ns = namespace(items=[]) %%}{%% for e in area_entities(%s) %%}' \
                       '{%% set ns.items = ns.items + [{"entity_id": e, "name": state_attr(e, "friendly_name")}] %%}' \
                       '{%% endfor %%}{{ ns.items | tojson }}' % json.dumps(params.get('area') or '')
            found = self._ha_request(params, 'POST', '/api/template', {'template': template})
            entities = json.loads(found) if isinstance(found, str) else found
            self.state['ha_discovered'] = {'area': params.get('area'), 'entities': entities}
            return 'Found %s devices' % len(entities or [])
        else:
            raise RuntimeError('Unknown room device.')

    def do_self_test(self, params):
        driver = self._in_call_driver()
        return json.dumps(driver.call('selfTest'))[:240]

    def do_admit_share(self, params):
        return 'Wireless share connecting'

    def _ha_request(self, connection, method, path, payload=None):
        request = urllib.request.Request(
            connection['url'].rstrip('/') + path, method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Authorization': 'Bearer %s' % connection['token'], 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode() or 'null'
        return json.loads(body) if body.strip()[:1] in '[{"' else body

    def home_assistant_sync(self):
        """Read the room's devices (every 10 s) and publish the room's status sensor."""
        connection = self.room.get('ha')
        if not connection:
            return
        try:
            if time.time() - self.ha_read_at >= 10:
                self.ha_read_at = time.time()
                states = {}
                for entity in connection.get('entities') or []:
                    data = self._ha_request(connection, 'GET', '/api/states/%s' % entity)
                    attrs = data.get('attributes') or {}
                    states[entity] = {'state': data.get('state'), 'attributes': {
                        k: attrs[k] for k in ('friendly_name', 'brightness', 'current_temperature', 'temperature',
                                              'current_position', 'hvac_mode') if k in attrs}}
                self.state['ha_states'] = states
                self.state['ha_status'] = 'Connected'
            status = self.room.get('status') or {}
            if connection.get('publish') and connection.get('sensor'):
                sensor = {'state': status.get('availability') or 'unknown', 'attributes': {
                    'friendly_name': '%s status' % self.room.get('room', 'Room'),
                    'in_call': bool(status.get('call')), 'do_not_disturb': bool((status.get('dnd') or {}).get('active')),
                    'current_booking': (status.get('current') or {}).get('title', ''),
                    'next_booking': (status.get('next') or {}).get('start', ''), 'icon': 'mdi:video-account'}}
                if sensor != self.ha_published:
                    self._ha_request(connection, 'POST', '/api/states/%s' % connection['sensor'], sensor)
                    self.ha_published = sensor
        except (urllib.error.URLError, OSError, ValueError) as error:
            self.state['ha_status'] = 'Home Assistant unreachable: %s' % str(error)[:80]

    def home_assistant(self, params):
        """Call a Home Assistant action on the local network (address and token come from Odoo)."""
        url = '%s/api/services/%s/%s' % (params['url'].rstrip('/'), params['domain'], params['service'])
        request = urllib.request.Request(url, data=json.dumps(params.get('data') or {}).encode(), method='POST',
                                         headers={'Authorization': 'Bearer %s' % params['token'],
                                                  'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
        return 'Done'

    # ── Call progress ────────────────────────────────────────────────────
    def advance_call(self):
        if not self.call:
            return
        driver = self.browser.driver('call')
        if not driver:
            return
        call = self.call
        info = driver.call('state') or {}
        page_state = info.get('state')
        if page_state in ('prejoin', 'idle', None) and time.time() - call['last_step'] >= STEP_EVERY:
            call['last_step'] = time.time()
            info = driver.call('step', call['params']) or info
            page_state = info.get('state') or page_state
        if page_state in ('lobby', 'in_call', 'error', 'ended'):
            call['state'] = page_state
        if page_state == 'in_call' and not self.companion and self.shared_group():
            self.start_companion()
        if page_state == 'error':
            self.state['error'] = info.get('error') or 'The platform refused the room.'
        elif call['state'] == 'prejoin' and time.time() - call['started'] > JOIN_TIMEOUT:
            page_state = 'error'
            self.state['error'] = 'The room couldn\'t join in 10 minutes: check the link, or whether the host lets guests in.'
        self.state.update(call_state=page_state or call['state'], mic=info.get('mic'), camera=info.get('camera'),
                          sharing=bool(info.get('sharing')))
        if page_state == 'ended':
            self.end_call()

    def start_companion(self):
        """A second, silent guest pinned to the shared content, on the Shared Content screens."""
        group = self.shared_group()
        params = dict(self.call['params'], mic=False, camera=False,
                      display_name='%s (content)' % self.call['params'].get('display_name', 'Room'))
        self.browser.window('companion', 'about:blank', group['rect'])
        driver = self.browser.driver('companion')
        driver.use_platform(params['driver'])
        driver.navigate(params['url'])
        self.companion = True

        def keep_going():
            for _ in range(300):
                if not self.call:
                    return
                state = (driver.call('step', params) or {}).get('state')
                driver.call('silence')
                if state == 'in_call':
                    driver.call('setLayout', 'content')
                    return
                time.sleep(2)
        threading.Thread(target=keep_going, daemon=True).start()

    def refresh_state(self):
        self.state['hdmi_present'] = bool(devices.hdmi_capture(self.config))
        self.state['video_devices'] = [name for _path, name in devices.video_devices()][:6]
        if self.state.get('volume') is None:
            self.state['volume'] = devices.get_volume()


if __name__ == '__main__':
    RoomDisplay().run()

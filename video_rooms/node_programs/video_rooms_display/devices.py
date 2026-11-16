# -*- coding: utf-8 -*-
"""The room PC's own devices: screens (xrandr), volume (PipeWire/PulseAudio), TV
power (HDMI-CEC, RS-232 or LAN), camera presets (v4l2) and the HDMI capture card."""
import codecs
import json
import logging
import os
import re
import socket
import subprocess

_logger = logging.getLogger('video_rooms.devices')

WALL_ORDER = ('front', 'left', 'right', 'back')
CAPTURE_NAMES = re.compile(r'capture|hdmi|cam link|ms21\d\d|usb3\.0 video|av to usb|elgato|magewell', re.I)


def session_env():
    """Environment for talking to the Node user's desktop (X11) and audio."""
    uid = os.getuid()
    env = dict(os.environ)
    env.setdefault('DISPLAY', ':0')
    env.setdefault('XDG_RUNTIME_DIR', '/run/user/%s' % uid)
    if 'XAUTHORITY' not in env:
        for path in ('/run/user/%s/gdm/Xauthority' % uid, os.path.expanduser('~/.Xauthority')):
            if os.path.exists(path):
                env['XAUTHORITY'] = path
                break
    return env


def run(args, input_text=None, timeout=10):
    result = subprocess.run(args, input=input_text, capture_output=True, text=True, timeout=timeout, env=session_env())
    if result.returncode:
        raise RuntimeError('%s: %s' % (args[0], (result.stderr or result.stdout).strip()[:200]))
    return result.stdout


# ── Screens ──────────────────────────────────────────────────────────────

def outputs():
    """{name: {'connected': bool, 'mode': (w, h)}} from xrandr."""
    found = {}
    current = None
    try:
        text = run(['xrandr', '--query'])
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return found
    for line in text.splitlines():
        match = re.match(r'^(\S+) (connected|disconnected)', line)
        if match:
            current = match.group(1)
            found[current] = {'connected': match.group(2) == 'connected', 'mode': None}
            continue
        mode = re.match(r'^\s+(\d+)x(\d+)\S*\s+.*\+', line)  # the preferred mode is marked with +
        if current and mode and found[current]['mode'] is None:
            found[current]['mode'] = (int(mode.group(1)), int(mode.group(2)))
    return found


def plan_layout(screens, available):
    """Where each screen goes. Returns (xrandr arguments, groups, rects): groups is a list of
    {'content', 'screens', 'rect': (x, y, w, h)} for the windows to place; rects is each
    screen's own rectangle {screen id: (x, y, w, h)} (mirrors share their screen's).

    Walls are laid side by side (front, left, right, back). On a wall, each screen sits
    at its grid cell. The first wall with Call screens hosts the meeting; Call screens on
    other walls mirror it. Mirror screens copy their screen (--same-as)."""
    args = ['xrandr']
    rects = {}
    wall_x = 0
    call_wall = next((w for w in WALL_ORDER if any(s['wall'] == w and s['content'] == 'call' for s in screens)), None)
    placed = [s for s in screens if s['output'] in available and available[s['output']]['mode']
              and s['content'] != 'mirror' and not (s['content'] == 'call' and s['wall'] != call_wall)]
    for wall in WALL_ORDER:
        on_wall = [s for s in placed if s['wall'] == wall]
        if not on_wall:
            continue
        unit_w = max(available[s['output']]['mode'][0] / max(1, s['w']) for s in on_wall)
        unit_h = max(available[s['output']]['mode'][1] / max(1, s['h']) for s in on_wall)
        width = 0
        for s in on_wall:
            mw, mh = available[s['output']]['mode']
            x, y = wall_x + int(s['x'] * unit_w), int(s['y'] * unit_h)
            rects[s['id']] = (x, y, mw, mh)
            args += ['--output', s['output'], '--mode', '%dx%d' % (mw, mh), '--pos', '%dx%d' % (x, y), '--rotate', 'normal']
            width = max(width, x - wall_x + mw)
        wall_x += width
    primary = None
    for s in screens:
        if s['output'] not in available or not available[s['output']]['connected']:
            continue
        target = None
        if s['content'] == 'mirror':
            target = next((t for t in screens if t['id'] == s.get('mirror_of')), None)
        elif s['content'] == 'call' and s['wall'] != call_wall:
            target = next((t for t in placed if t['content'] == 'call'), None)
        if target and target['id'] in rects:
            args += ['--output', s['output'], '--auto', '--same-as', target['output']]
        if s['content'] == 'call' and s['id'] in rects and not primary:
            primary = s['output']
    if primary:
        args += ['--output', primary, '--primary']
    used = {s['output'] for s in screens}
    for name, info in available.items():
        if name not in used and info['connected']:
            args += ['--output', name, '--off']
    for s in screens:
        target = next((t for t in screens if t['id'] == s.get('mirror_of')), None) if s['content'] == 'mirror' else None
        if target and target['id'] in rects:
            rects[s['id']] = rects[target['id']]
    groups = []
    calls = [s for s in placed if s['content'] == 'call']
    if calls:
        groups.append({'content': 'call', 'screens': [s['id'] for s in calls], 'rect': _bounds([rects[s['id']] for s in calls])})
    for content in ('shared', 'info'):
        for s in placed:
            if s['content'] == content:
                groups.append({'content': content, 'screens': [s['id']], 'rect': rects[s['id']]})
    return args, groups, rects


def _bounds(rects):
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[0] + r[2] for r in rects)
    y1 = max(r[1] + r[3] for r in rects)
    return (x0, y0, x1 - x0, y1 - y0)


def apply_layout(screens):
    """Arrange the outputs; returns (window groups, screen rectangles) - see plan_layout."""
    available = outputs()
    args, groups, rects = plan_layout(screens, available)
    if len(args) > 1:
        try:
            run(args, timeout=20)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            _logger.warning('Arranging the screens failed: %s', error)
    if not groups:
        # Nothing configured yet: one window on the whole desktop.
        groups = [{'content': 'call', 'screens': [], 'rect': None}]
    return groups, rects


# ── Audio ────────────────────────────────────────────────────────────────

def get_volume():
    try:
        match = re.search(r'(\d+)%', run(['pactl', 'get-sink-volume', '@DEFAULT_SINK@']))
        return int(match.group(1)) if match else None
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return None


def set_volume(percent):
    percent = max(0, min(100, int(percent)))
    run(['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '%d%%' % percent])
    return percent


# ── TV power ─────────────────────────────────────────────────────────────

def _bytes(text):
    return codecs.decode(text or '', 'unicode_escape').encode('latin-1')


def tv_power(on, control, screens):
    method = (control or {}).get('method') or 'none'
    if method == 'none':
        raise RuntimeError('The room\'s TVs are not controlled (set a TV Power Control on the room).')
    if method == 'cec':
        run(['cec-client', '-s', '-d', '1'], input_text='on 0\n' if on else 'standby 0\n', timeout=20)
        return
    command = _bytes(control.get('on') if on else control.get('off'))
    if not command:
        raise RuntimeError('The TV control type has no %s command.' % ('on' if on else 'off'))
    addresses = [s.get('tv_address') for s in screens if s.get('tv_address')]
    if method == 'ip':
        if not addresses:
            raise RuntimeError('Set each screen\'s TV Address (e.g. 192.168.1.50:9761).')
        for address in addresses:
            host, _, port = address.rpartition(':')
            with socket.create_connection((host, int(port)), timeout=5) as conn:
                conn.sendall(command)
        return
    if method == 'rs232':
        import termios  # Linux only
        devices = addresses or ['/dev/ttyUSB0']
        for device in devices:
            fd = os.open(device, os.O_RDWR | os.O_NOCTTY)
            try:
                attrs = termios.tcgetattr(fd)
                attrs[4] = attrs[5] = termios.B9600
                attrs[2] = (attrs[2] & ~termios.CSIZE & ~termios.PARENB & ~termios.CSTOPB) | termios.CS8 | termios.CREAD | termios.CLOCAL
                attrs[3] = 0
                termios.tcsetattr(fd, termios.TCSANOW, attrs)
                os.write(fd, command)
            finally:
                os.close(fd)


# ── Cameras and HDMI capture ─────────────────────────────────────────────

def video_devices():
    """[(path, name)] of the V4L2 devices that capture video."""
    found = []
    base = '/sys/class/video4linux'
    for entry in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        try:
            with open(os.path.join(base, entry, 'name')) as file:
                name = file.read().strip()
            with open(os.path.join(base, entry, 'index')) as file:
                if file.read().strip() != '0':
                    continue  # metadata nodes
        except OSError:
            continue
        found.append(('/dev/%s' % entry, name))
    return found


def hdmi_capture(config):
    """The HDMI capture card's name, if one is plugged in."""
    wanted = (config.get('hdmi_capture_name') or '').lower()
    for _path, name in video_devices():
        if (wanted and wanted in name.lower()) or (not wanted and CAPTURE_NAMES.search(name)):
            return name
    return None


def room_camera(config):
    capture = hdmi_capture(config)
    for path, name in video_devices():
        if name != capture:
            return path
    return None


def ptz_recall(preset, config, data_dir):
    """Move the camera to a saved preset (data/ptz_presets.json: {"1": {"pan_absolute": 0, ...}})."""
    path = os.path.join(data_dir, 'ptz_presets.json')
    try:
        with open(path) as file:
            presets = json.load(file)
    except (OSError, ValueError):
        presets = {}
    values = presets.get(str(preset))
    if not values:
        raise RuntimeError('Camera preset %s isn\'t saved yet.' % preset)
    camera = room_camera(config)
    if not camera:
        raise RuntimeError('No room camera found.')
    run(['v4l2-ctl', '-d', camera, '-c', ','.join('%s=%s' % (k, int(v)) for k, v in values.items())])


def ptz_save(preset, config, data_dir):
    camera = room_camera(config)
    if not camera:
        raise RuntimeError('No room camera found.')
    current = {}
    for line in run(['v4l2-ctl', '-d', camera, '-C', 'pan_absolute,tilt_absolute,zoom_absolute']).splitlines():
        key, _, value = line.partition(':')
        if value.strip().lstrip('-').isdigit():
            current[key.strip()] = int(value)
    path = os.path.join(data_dir, 'ptz_presets.json')
    try:
        with open(path) as file:
            presets = json.load(file)
    except (OSError, ValueError):
        presets = {}
    presets[str(preset)] = current
    with open(path, 'w') as file:
        json.dump(presets, file)

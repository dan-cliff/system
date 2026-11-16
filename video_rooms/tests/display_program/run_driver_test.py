"""Room Display program check (not part of Odoo's test run).

Drives a stand-in Teams page (mock_teams.html) with the Room Display's real cdp.py,
drivers and PageDriver in a headless Chrome, and checks the screen layout planning:

    python3 video_rooms/tests/display_program/run_driver_test.py /path/to/chrome
"""
import json
import os
import subprocess
import sys
import time

PROGRAM = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'node_programs', 'video_rooms_display')
sys.path.insert(0, PROGRAM)
os.environ['IOT_PROGRAM_DIR'] = PROGRAM
import cdp  # noqa: E402
import devices  # noqa: E402
import room_agent  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
server = subprocess.Popen([sys.executable, '-m', 'http.server', '8765', '--bind', '127.0.0.1'], cwd=HERE,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
chrome = subprocess.Popen([sys.argv[1] if len(sys.argv) > 1 else 'google-chrome-stable',
                           '--headless=new', '--no-sandbox', '--remote-debugging-port=9222', '--remote-allow-origins=*',
                           '--user-data-dir=/tmp/vr-chrome-test', 'about:blank'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
failures = []


def check(label, condition, detail=''):
    print(('PASS ' if condition else 'FAIL ') + label + (' ' + str(detail) if detail else ''))
    if not condition:
        failures.append(label)


try:
    for _ in range(50):
        if cdp.browser_available():
            break
        time.sleep(0.2)
    browser = room_agent.Browser()
    check('browser connects over DevTools', browser.ready())
    driver = browser.driver("call")
    driver.use_platform('teams')
    driver.navigate('http://127.0.0.1:8765/mock_teams.html')
    params = {'display_name': "Cliff's Country Crafts - Board Room", 'mic': True, 'camera': False}
    states = []
    for _ in range(20):
        time.sleep(1)
        info = driver.call('state') or {}
        if info.get('state') in ('prejoin', 'idle', None):
            info = driver.call('step', params) or info
        states.append(info.get('state'))
        if info.get('state') == 'in_call':
            break
    check('joins: launcher -> pre-join -> lobby -> in call', 'in_call' in states and 'lobby' in states, states)
    events = json.loads(driver.session.call('Runtime.evaluate', {'expression': 'JSON.stringify(window.events)', 'returnByValue': True})['result']['value'])
    joined = [e for e in events if e.startswith('join')]
    check('name typed and camera switched off before joining', joined and "Board Room" in joined[0] and 'cam=false' in joined[0], joined)
    check('join click is a trusted (user) click', joined and 'trusted=true' in joined[0], joined)
    info = driver.call('state')
    check('mic reported on', info.get('mic') is True, info)
    driver.call('setMic', False)
    time.sleep(0.3)
    check('mic switched off', driver.call('state').get('mic') is False, driver.call('state'))
    driver.call('startShare', 'Video Rooms Share')
    time.sleep(1)
    events = json.loads(driver.session.call('Runtime.evaluate', {'expression': 'JSON.stringify(window.events)', 'returnByValue': True})['result']['value'])
    check('share click is trusted (screen sharing needs a user gesture)', any(e == 'share trusted=true' for e in events), events)
    driver.call('leave')
    time.sleep(0.5)
    check('leaving ends the call', driver.call('state').get('state') == 'ended', driver.call('state'))
    test = driver.call('selfTest')
    check('self-test reports selectors', isinstance(test, dict) and 'found' in test)
finally:
    chrome.terminate()
    server.terminate()

# Screen layout planning (no X needed).
available = {'HDMI-1': {'connected': True, 'mode': (1920, 1080)}, 'HDMI-2': {'connected': True, 'mode': (1920, 1080)},
             'DP-1': {'connected': True, 'mode': (1920, 1080)}, 'DP-2': {'connected': True, 'mode': (3840, 2160)}}
screens = [
    {'id': 1, 'output': 'HDMI-1', 'wall': 'front', 'x': 0, 'y': 0, 'w': 1, 'h': 1, 'content': 'call'},
    {'id': 2, 'output': 'HDMI-2', 'wall': 'front', 'x': 1, 'y': 0, 'w': 1, 'h': 1, 'content': 'call'},
    {'id': 3, 'output': 'DP-1', 'wall': 'left', 'x': 0, 'y': 0, 'w': 1, 'h': 1, 'content': 'mirror', 'mirror_of': 1},
    {'id': 4, 'output': 'DP-2', 'wall': 'back', 'x': 0, 'y': 0, 'w': 1, 'h': 1, 'content': 'info'},
]
args, groups, rects = devices.plan_layout(screens, available)
call = next(g for g in groups if g['content'] == 'call')
check('two front Call screens span one 3840x1080 canvas', call['rect'] == (0, 0, 3840, 1080), call)
check('mirror uses --same-as its screen', ' '.join(args).count('--output DP-1 --auto --same-as HDMI-1') == 1, args)
check('room info screen gets its own window', any(g['content'] == 'info' and g['rect'][0] >= 3840 for g in groups), groups)
check('the mirror is identified where its screen is', rects.get(3) == rects.get(1), rects)
print('FAILURES:', failures)
sys.exit(1 if failures else 0)

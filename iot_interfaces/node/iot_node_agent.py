#!/usr/bin/env python3
"""IoT Node agent - the base program on every Node (Raspberry Pi).

Odoo is hosted outside the local network, so it can't reach the hardware
here. The agent makes every connection from the Node out to Odoo over
HTTPS (nothing is opened on the router) and:

* pairs the Node once with a one-time code, then signs every request with
  the Node's rolling key (see iot_auth.py); it is the only process that
  holds the key;
* checks in with Odoo every 30 seconds: keeps the Node shown online, picks
  up a new key when Odoo replaces it, and learns which version of the
  role's program the Node should run;
* updates that program over the air: downloads the files, checks every
  checksum, switches to the new version, and rolls back if it keeps
  crashing;
* starts the program and keeps it running;
* serves http://127.0.0.1:8099/ on the Node only: the program (and
  Chromium, for screens) reach Odoo through it, and it signs their
  requests. / opens the program's home page.

    python3 iot_node_agent.py --config /etc/iot-node/config.json --pair ABCD-EFGH-JKLM-NPQR
    python3 iot_node_agent.py --config /etc/iot-node/config.json --update-once
    python3 iot_node_agent.py --config /etc/iot-node/config.json
"""
import argparse
import collections
import hashlib
import html
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import iot_auth
except ImportError:  # running from the Odoo module's source
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
    import iot_auth

VERSION = '1.0.0'
DEFAULT_PORT = 8099
HELLO_SECONDS = 30
# A new version that crashes this many times within PROBATION_SECONDS is rolled back.
CRASHES_BEFORE_ROLLBACK = 3
PROBATION_SECONDS = 120
MAX_RESTART_DELAY = 60

_logger = logging.getLogger('iot_node_agent')

WAITING_PAGE = '''<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="10">
<link rel="icon" href="data:,"><title>Node</title><style>body{margin:0;height:100vh;display:flex;
align-items:center;justify-content:center;background:#0f1218;color:#9aa3b5;font:3.5vh sans-serif;
text-align:center;cursor:none}</style></head><body><div>%s<br><small>%s</small></div></body></html>'''


def files_digest(files):
    """Same checksum Odoo computes over a version's files: {path: sha256}."""
    lines = ''.join('%s\0%s\n' % (path, files[path]) for path in sorted(files))
    return hashlib.sha256(lines.encode()).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as file:
        for chunk in iter(lambda: file.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


class State:
    """What the Node runs, kept in installed.json."""

    def __init__(self, path):
        self.path = path
        self.data = {}
        if os.path.exists(path):
            with open(path, encoding='utf-8') as file:
                self.data = json.load(file)

    def __getitem__(self, key):
        return self.data.get(key)

    def update(self, **values):
        self.data.update(values)
        tmp = self.path + '.new'
        with open(tmp, 'w', encoding='utf-8') as file:
            json.dump(self.data, file, indent=4)
        os.replace(tmp, self.path)


class Agent:
    def __init__(self, config):
        self.config = config
        self.state_dir = config['state_dir']
        self.programs_dir = os.path.join(self.state_dir, 'programs')
        self.current_link = os.path.join(self.state_dir, 'program')
        os.makedirs(self.programs_dir, exist_ok=True)
        os.makedirs(os.path.join(self.state_dir, 'data'), exist_ok=True)
        self.client = iot_auth.NodeClient(config['odoo_url'], os.path.join(self.state_dir, 'credentials.json'),
                                          user_agent='IoTNodeAgent/%s' % VERSION, timeout=config.get('timeout', 30))
        self.state = State(os.path.join(self.state_dir, 'installed.json'))
        self.home = self.state['home'] or ''
        self.child = None
        self.child_output = collections.deque(maxlen=30)
        self.crashes = []
        self.probation_until = 0
        self.restart_at = 0
        self.restart_delay = 5
        self.lock = threading.RLock()
        self.last_hello_ok = 0

    # ── Odoo check-in ─────────────────────────────────────────────────────
    def hello(self):
        report = {
            'digest': self.state['digest'] or '',
            'version_id': self.state['version_id'],
            'error': self.state['error'] or '',
            'setup_changed': bool(self.state['setup_changed']),
        }
        result = self.client.hello(VERSION, program=report, hostname=os.uname().nodename)
        self.last_hello_ok = time.time()
        return result

    def apply(self, target):
        """Bring the program up to ``target`` (the check-in's 'program'). Returns True if it changed."""
        if not target:
            return False
        self.home = target.get('home') or ''
        setup_changed = bool(target.get('setup_sha256')) and \
            target.get('setup_sha256') != self.state['setup_applied_sha256']
        if setup_changed != bool(self.state['setup_changed']):
            self.state.update(setup_changed=setup_changed)
        if target['digest'] == self.state['digest']:
            if self.state['home'] != self.home:
                self.state.update(home=self.home)
            if self.state['error']:
                # Odoo is back on the version we run (e.g. after a rollback).
                self.state.update(error='', failed_digest=None)
            return False
        if target['digest'] == self.state['failed_digest']:
            return False  # already rolled back from it; wait for a different version
        _logger.info('Updating to %s', target.get('name'))
        try:
            folder = self.download(target)
        except Exception as error:  # report it; the current version keeps running
            _logger.warning('Update to %s failed: %s', target.get('name'), error)
            self.state.update(error='Download of %s failed: %s' % (target.get('name'), error))
            return False
        self.switch(folder, target)
        return True

    def download(self, target):
        folder = os.path.join(self.programs_dir, target['digest'][:16])
        if os.path.isdir(folder) and self._folder_digest(folder, target) == target['digest']:
            return folder
        staging = folder + '.staging'
        shutil.rmtree(staging, ignore_errors=True)
        current = os.path.realpath(self.current_link) if os.path.islink(self.current_link) else None
        hashes = {}
        for file in target['files']:
            path = os.path.normpath(file['path'])
            if path.startswith(('..', '/')):
                raise ValueError('unsafe path %s' % file['path'])
            dest = os.path.join(staging, path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            local = os.path.join(current, path) if current else None
            if local and os.path.isfile(local) and sha256_file(local) == file['sha256']:
                shutil.copy2(local, dest)  # unchanged file: no need to download it
            else:
                status, _headers, data = self.client.request('GET', file['url'])
                if status != 200:
                    raise ValueError('%s: HTTP %s' % (file['path'], status))
                with open(dest, 'wb') as out:
                    out.write(data)
            hashes[file['path']] = sha256_file(dest)
            if hashes[file['path']] != file['sha256']:
                raise ValueError('%s: checksum does not match' % file['path'])
            if path.endswith('.sh') or path == target.get('entrypoint'):
                os.chmod(dest, 0o755)
        if files_digest(hashes) != target['digest']:
            raise ValueError('the version checksum does not match')
        shutil.rmtree(folder, ignore_errors=True)
        os.replace(staging, folder)
        return folder

    @staticmethod
    def _folder_digest(folder, target):
        try:
            return files_digest({f['path']: sha256_file(os.path.join(folder, f['path'])) for f in target['files']})
        except OSError:
            return None

    def switch(self, folder, target):
        with self.lock:
            previous = os.path.realpath(self.current_link) if os.path.islink(self.current_link) else None
            self.stop_child()
            tmp_link = self.current_link + '.new'
            if os.path.lexists(tmp_link):
                os.unlink(tmp_link)
            os.symlink(folder, tmp_link)
            os.replace(tmp_link, self.current_link)
            self.state.update(
                digest=target['digest'], version_id=target['version_id'], name=target.get('name'),
                entrypoint=target.get('entrypoint') or '', home=target.get('home') or '',
                previous=previous if previous != folder else self.state['previous'],
                previous_state={k: self.state[k] for k in ('digest', 'version_id', 'name', 'entrypoint', 'home')},
                error='',
            )
            self.crashes = []
            self.probation_until = time.time() + PROBATION_SECONDS
            self.restart_at = 0
            self.cleanup()
            _logger.info('Now running %s', target.get('name'))

    def rollback(self, reason):
        with self.lock:
            failed = self.state['digest']
            previous = self.state['previous']
            prev_state = self.state['previous_state'] or {}
            self.stop_child()
            message = '%s %s' % (self.state['name'], reason)
            if previous and os.path.isdir(previous) and prev_state.get('digest'):
                tmp_link = self.current_link + '.new'
                if os.path.lexists(tmp_link):
                    os.unlink(tmp_link)
                os.symlink(previous, tmp_link)
                os.replace(tmp_link, self.current_link)
                message += '; rolled back to %s' % prev_state.get('name')
                self.state.update(failed_digest=failed, previous=None, previous_state=None, error=message,
                                  **prev_state)
                self.home = prev_state.get('home') or ''
            else:
                message += '; no earlier version to roll back to'
                self.state.update(failed_digest=failed, error=message)
            _logger.error(message)
            self.crashes = []
            self.probation_until = 0
            self.restart_delay = 5

    def cleanup(self):
        keep = {os.path.realpath(self.current_link), self.state['previous']}
        for name in os.listdir(self.programs_dir):
            path = os.path.join(self.programs_dir, name)
            if os.path.realpath(path) not in keep:
                shutil.rmtree(path, ignore_errors=True)

    # ── Running the program ───────────────────────────────────────────────
    def start_child(self):
        entrypoint = self.state['entrypoint']
        if not entrypoint or not os.path.islink(self.current_link):
            return
        folder = os.path.realpath(self.current_link)
        env = dict(os.environ,
                   IOT_PROXY_URL='http://127.0.0.1:%s' % self.config['port'],
                   IOT_PROGRAM_DIR=folder,
                   IOT_DATA_DIR=os.path.join(self.state_dir, 'data'),
                   IOT_NODE_NAME=self.client.credentials.data.get('name', ''),
                   PYTHONUNBUFFERED='1')
        command = [sys.executable, entrypoint] if entrypoint.endswith('.py') else [os.path.join(folder, entrypoint)]
        _logger.info('Starting %s', entrypoint)
        self.child_output.clear()
        self.child = subprocess.Popen(command, cwd=folder, env=env, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, bufsize=1)
        threading.Thread(target=self._pipe_output, args=(self.child,), daemon=True).start()

    def _pipe_output(self, child):
        for line in child.stdout:
            line = line.rstrip()
            self.child_output.append(line)
            print('[program] %s' % line, flush=True)

    def stop_child(self):
        child, self.child = self.child, None
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(10)
            except subprocess.TimeoutExpired:
                child.kill()

    def supervise(self):
        """Keep the program running; roll a new version back if it keeps crashing."""
        with self.lock:
            now = time.time()
            if self.child and self.child.poll() is not None:
                code = self.child.returncode
                self.child = None
                _logger.warning('The program stopped (exit code %s)', code)
                if now < self.probation_until:
                    self.crashes.append(now)
                    if len(self.crashes) >= CRASHES_BEFORE_ROLLBACK:
                        last = ' | '.join(list(self.child_output)[-5:])
                        self.rollback('kept crashing on start (%s)' % (last or 'exit code %s' % code))
                        self.restart_at = now
                        return
                self.restart_at = now + self.restart_delay
                self.restart_delay = min(self.restart_delay * 2, MAX_RESTART_DELAY)
            if not self.child and self.state['entrypoint'] and now >= self.restart_at:
                self.start_child()
                if now > self.probation_until:
                    self.restart_delay = 5

    # ── Main loops ────────────────────────────────────────────────────────
    def run(self):
        server = ThreadingHTTPServer(('127.0.0.1', int(self.config['port'])), make_handler(self))
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _logger.info('IoT Node agent %s for %s, local address http://127.0.0.1:%s/',
                     VERSION, self.client.url, self.config['port'])
        next_hello = 0
        while True:
            if time.time() >= next_hello:
                next_hello = time.time() + HELLO_SECONDS
                try:
                    result = self.hello()
                    if self.apply(result.get('program')):
                        next_hello = time.time()  # report the new version straight away
                except iot_auth.NodeError as error:
                    if error.status == 401:
                        _logger.error('Odoo refused this Node: %s', error)
                    else:
                        _logger.warning('Check-in failed: %s', error)
            self.supervise()
            time.sleep(1)


def make_handler(agent):
    class Handler(BaseHTTPRequestHandler):
        """http://127.0.0.1:<port>/ - signs and forwards requests to Odoo."""

        def log_message(self, format, *args):  # noqa: A002 - BaseHTTPRequestHandler's signature
            _logger.debug('%s %s', self.address_string(), format % args)

        def _send(self, status, body, headers):
            self.send_response(status)
            for key, value in headers:
                self.send_header(key, value)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _page(self, title, detail, status=200):
            page = WAITING_PAGE % (html.escape(title), html.escape(detail))
            self._send(status, page.encode(), [('Content-Type', 'text/html; charset=utf-8')])

        def _wants_html(self):
            return 'text/html' in (self.headers.get('Accept') or '')

        def _forward(self, method):
            if self.path == '/_node/status':
                status = {'agent': VERSION, 'paired': agent.client.paired, 'program': agent.state['name'],
                          'error': agent.state['error'], 'online': time.time() - agent.last_hello_ok < 90}
                self._send(200, json.dumps(status).encode(), [('Content-Type', 'application/json')])
                return
            if self.path == '/' and agent.home:
                self._send(302, b'', [('Location', agent.home)])
                return
            if not agent.client.paired:
                self._page('This Node is not paired with Odoo yet.', 'Run the install command from Odoo on it.', 503)
                return
            if self.path == '/':
                self._page(agent.client.credentials.data.get('name') or 'IoT Node',
                           'Running %s' % (agent.state['name'] or 'no program yet'))
                return
            length = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(length) if length else None
            try:
                status, headers, data = agent.client.request(method, self.path, body)
            except iot_auth.NodeError as error:
                if self._wants_html():
                    self._page('Waiting for Odoo…', 'Check the network connection.')
                else:
                    self._send(502, json.dumps({'status': 'error', 'message': str(error)}).encode(),
                               [('Content-Type', 'application/json')])
                return
            if status == 401 and self._wants_html():
                try:
                    message = json.loads(data.decode() or '{}').get('message', '')
                except ValueError:
                    message = ''
                self._page('Odoo refused this Node.', message)
                return
            passed = [(k, v) for k, v in headers.items() if k.lower() in ('content-type', 'cache-control', 'location')]
            self._send(status, data, passed)

        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
            self._forward('GET')

        def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
            self._forward('POST')

    return Handler


def load_config(path):
    with open(path, encoding='utf-8') as file:
        config = json.load(file)
    if not config.get('odoo_url'):
        raise SystemExit('%s is missing: odoo_url' % path)
    config.setdefault('port', DEFAULT_PORT)
    # A relative path is beside the config file.
    config['state_dir'] = os.path.join(os.path.dirname(os.path.abspath(path)), config.get('state_dir') or 'state')
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--config', default='/etc/iot-node/config.json')
    parser.add_argument('--pair', metavar='CODE', help='pair this Node with Odoo using a one-time pairing code')
    parser.add_argument('--update-once', action='store_true',
                        help='check in, install the program version Odoo says, print it as JSON and exit')
    parser.add_argument('--setup-applied', metavar='SHA256',
                        help='record that the install command ran the setup script with this checksum')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)
    config = load_config(args.config)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', datefmt='%d/%m/%Y %H:%M:%S',
                        handlers=[logging.StreamHandler(sys.stderr)])
    agent = Agent(config)
    if args.pair:
        try:
            result = agent.client.pair(args.pair, None, VERSION)
        except iot_auth.NodeError as error:
            raise SystemExit(str(error))
        _logger.info('Paired with Odoo as "%s" (%s), MAC %s', result.get('name'), result.get('role'), agent.client.mac)
        return
    if args.setup_applied is not None:
        agent.state.update(setup_applied_sha256=args.setup_applied, setup_changed=False)
        return
    if not agent.client.paired:
        raise SystemExit('This Node is not paired with Odoo yet: run it with --pair and the code from Odoo.')
    if args.update_once:
        result = agent.hello()
        target = result.get('program')
        agent.apply(target)
        print(json.dumps({
            'role': result.get('role'),
            'program': agent.state['name'],
            'folder': os.path.realpath(agent.current_link) if os.path.islink(agent.current_link) else '',
            'setup': (target or {}).get('setup') or '',
            'setup_sha256': (target or {}).get('setup_sha256') or '',
            'error': agent.state['error'] or '',
        }))
        return
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    try:
        agent.run()
    except (KeyboardInterrupt, SystemExit):
        agent.stop_child()
        _logger.info('Stopped')


if __name__ == '__main__':
    main()

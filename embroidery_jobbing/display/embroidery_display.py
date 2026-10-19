#!/usr/bin/env python3
"""Embroidery Display - shows an Odoo machine status board on a TV.

Runs on a Raspberry Pi plugged into the TV. Chromium on the Pi opens
http://127.0.0.1:8099/ full screen; this agent serves that page by fetching
it from Odoo, signing every request with the key the Pi got when it was
paired (see embroidery_auth.py). So the screen needs no login and no secret
address, and only paired, authorised Pis can show it. Odoo replaces the key
from time to time without the Pi having to be paired again.

Which board the screen shows, and how, is set on the Display in Odoo.

    python3 embroidery_display.py --config config.json --pair ABCD-EFGH-JKLM-NPQR
    python3 embroidery_display.py --config config.json
"""
import argparse
import html
import json
import logging
import os
import re
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import embroidery_auth
except ImportError:  # running from the Odoo module's source
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
    import device_auth as embroidery_auth

VERSION = '1.0.0'
DEFAULT_PORT = 8099
HELLO_SECONDS = 60

_logger = logging.getLogger('embroidery_display')

# Paths Chromium asks for -> paths on Odoo. Nothing else is passed on.
ROUTES = [
    (re.compile(r'^/$'), lambda m: '/embroidery/pi/v1/display/page'),
    (re.compile(r'^/data\.json$'), lambda m: '/embroidery/pi/v1/display/data.json'),
    (re.compile(r'^/design/(\d+)$'), lambda m: '/embroidery/pi/v1/display/design/%s' % m.group(1)),
    (re.compile(r'^/logo\.png$'), lambda m: '/logo.png'),
    (re.compile(r'^(/embroidery_jobbing/static/src/status_page/[\w.]+)$'), lambda m: m.group(1)),
]
PASS_HEADERS = ('content-type', 'cache-control')

WAITING_PAGE = '''<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="10">
<link rel="icon" href="data:,">
<title>Machine Status</title><style>body{margin:0;height:100vh;display:flex;align-items:center;
justify-content:center;background:#0f1218;color:#9aa3b5;font:3.5vh sans-serif;text-align:center;cursor:none}
</style></head><body><div>%s<br><small>%s</small></div></body></html>'''


def upstream_path(path):
    route, _sep, query = path.partition('?')
    for pattern, target in ROUTES:
        match = pattern.match(route)
        if match:
            return target(match) + ('?' + query if query else '')
    return None


class Handler(BaseHTTPRequestHandler):
    client = None  # set in main()

    def log_message(self, format, *args):  # noqa: A002 - BaseHTTPRequestHandler's signature
        _logger.debug('%s %s', self.address_string(), format % args)

    def _send(self, status, body, headers):
        self.send_response(status)
        for key, value in headers:
            self.send_header(key, value)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _waiting(self, title, detail):
        page = WAITING_PAGE % (html.escape(title), html.escape(detail))
        self._send(503 if self.path != '/' else 200, page.encode(), [('Content-Type', 'text/html; charset=utf-8')])

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
        target = upstream_path(self.path)
        if target is None:
            self._send(404, b'Not found', [('Content-Type', 'text/plain')])
            return
        if not self.client.paired:
            self._waiting('This screen is not paired with Odoo yet.',
                          'In Odoo: Embroidery > Configuration > Displays > Pair a Raspberry Pi')
            return
        try:
            status, headers, body = self.client.request('GET', target)
        except embroidery_auth.DeviceError as error:
            _logger.warning('Odoo unreachable: %s', error)
            if self.path == '/':
                self._waiting('Waiting for Odoo…', 'Check the network connection.')
            else:
                self._send(502, json.dumps({'status': 'error', 'message': 'Odoo is unreachable.'}).encode(),
                           [('Content-Type', 'application/json')])
            return
        if status == 401 and self.path == '/':
            message = json.loads(body.decode() or '{}').get('message', '') if body.startswith(b'{') else ''
            self._waiting('Odoo refused this screen.', message)
            return
        self._send(status, body, [(k, v) for k, v in headers.items() if k.lower() in PASS_HEADERS])


def hello_loop(client):
    """Check in with Odoo: keeps the Pi shown as online and picks up new keys."""
    while True:
        if client.paired:
            try:
                client.request_json('POST', '/embroidery/pi/v1/display/hello', {'version': VERSION})
            except embroidery_auth.DeviceError as error:
                _logger.warning('Check-in with Odoo failed: %s', error)
        time.sleep(HELLO_SECONDS)


def load_config(path):
    with open(path, encoding='utf-8') as file:
        config = json.load(file)
    if not config.get('odoo_url'):
        raise SystemExit('%s is missing: odoo_url' % path)
    # A relative path is beside the config file.
    config['credentials'] = os.path.join(os.path.dirname(os.path.abspath(path)),
                                         config.get('credentials') or 'credentials.json')
    config.setdefault('port', DEFAULT_PORT)
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--config', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json'),
                        help='config file (default: config.json beside this script)')
    parser.add_argument('--pair', metavar='CODE', help='pair this Pi with Odoo using a one-time pairing code')
    parser.add_argument('--verbose', action='store_true', help='log more detail')
    args = parser.parse_args(argv)
    config = load_config(args.config)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', datefmt='%d/%m/%Y %H:%M:%S',
                        handlers=[logging.StreamHandler(sys.stdout)])
    client = embroidery_auth.DeviceClient(config['odoo_url'], config['credentials'],
                                          user_agent='EmbroideryDisplay/%s' % VERSION,
                                          timeout=config.get('timeout', 20))
    if args.pair:
        try:
            result = client.pair(args.pair, 'display', VERSION)
        except embroidery_auth.DeviceError as error:
            raise SystemExit(str(error))
        _logger.info('Paired with Odoo as "%s" (this Pi: %s)', result.get('name'), client.mac)
        return

    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    Handler.client = client
    server = ThreadingHTTPServer(('127.0.0.1', int(config['port'])), Handler)
    server.daemon_threads = True
    threading.Thread(target=hello_loop, args=(client,), daemon=True).start()
    _logger.info('Embroidery Display %s serving http://127.0.0.1:%s/ from %s', VERSION, config['port'], client.url)
    if not client.paired:
        _logger.warning('This Pi is not paired with Odoo yet: run it with --pair and the code from Odoo.')
    try:
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        _logger.info('Stopped')


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""A small Chrome DevTools Protocol client (standard library only).

The room's Chrome listens on 127.0.0.1:9222 (room_browser.sh). This drives it:
opening windows, placing them on the screens, injecting the platform drivers and
sending trusted clicks and keys (which screen sharing needs). Nothing here is
reachable from the network.
"""
import base64
import json
import logging
import os
import socket
import struct
import threading
import urllib.request

_logger = logging.getLogger('video_rooms.cdp')

HOST = '127.0.0.1'
PORT = 9222


class CdpError(Exception):
    pass


class WebSocket:
    """Just enough RFC 6455 for DevTools: text frames, ping/pong, close."""

    def __init__(self, url, timeout=10):
        assert url.startswith('ws://')
        hostport, _, path = url[5:].partition('/')
        host, _, port = hostport.partition(':')
        self.sock = socket.create_connection((host, int(port or 80)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        request = ('GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                   'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nOrigin: http://%s\r\n\r\n'
                   % (path, hostport, key, hostport))
        self.sock.sendall(request.encode())
        response = b''
        while b'\r\n\r\n' not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CdpError('DevTools closed the connection during the handshake.')
            response += chunk
        if b' 101 ' not in response.split(b'\r\n', 1)[0]:
            raise CdpError('DevTools refused the connection: %s' % response.split(b'\r\n', 1)[0].decode(errors='replace'))
        self.sock.settimeout(None)
        self._send_lock = threading.Lock()
        self._buffer = response.split(b'\r\n\r\n', 1)[1]

    def send(self, text):
        payload = text.encode()
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += struct.pack('!H', length)
        else:
            header.append(0x80 | 127)
            header += struct.pack('!Q', length)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self._send_lock:
            self.sock.sendall(bytes(header) + mask + masked)

    def _read(self, n):
        while len(self._buffer) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise CdpError('DevTools connection closed.')
            self._buffer += chunk
        data, self._buffer = self._buffer[:n], self._buffer[n:]
        return data

    def recv(self):
        """The next text message (str), or None when the connection closes."""
        parts = []
        while True:
            first, second = self._read(2)
            fin, opcode = first & 0x80, first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = struct.unpack('!H', self._read(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', self._read(8))[0]
            if second & 0x80:
                mask = self._read(4)
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(self._read(length)))
            else:
                payload = self._read(length)
            if opcode == 0x8:
                return None
            if opcode == 0x9:  # ping
                with self._send_lock:
                    self.sock.sendall(bytes([0x8A, 0x80 | len(payload)]) + b'\0\0\0\0' + payload)
                continue
            if opcode in (0x0, 0x1, 0x2):
                parts.append(payload)
                if fin:
                    return b''.join(parts).decode(errors='replace')

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Session:
    """A DevTools connection (to the browser or to one page) with request/response
    matching and event handlers."""

    def __init__(self, ws_url, name=''):
        self.name = name
        self.ws = WebSocket(ws_url)
        self._id = 0
        self._pending = {}
        self._lock = threading.Lock()
        self.handlers = {}  # event method -> [callback(params)]
        self.alive = True
        self._thread = threading.Thread(target=self._loop, name='cdp-%s' % name, daemon=True)
        self._thread.start()

    def _loop(self):
        try:
            while True:
                message = self.ws.recv()
                if message is None:
                    break
                data = json.loads(message)
                if 'id' in data:
                    waiter = self._pending.pop(data['id'], None)
                    if waiter:
                        waiter['result'] = data
                        waiter['event'].set()
                else:
                    for callback in self.handlers.get(data.get('method'), []):
                        try:
                            callback(data.get('params') or {})
                        except Exception:  # a handler must never kill the loop
                            _logger.exception('DevTools event handler failed')
        except (CdpError, OSError, ValueError) as error:
            _logger.info('DevTools session %s ended: %s', self.name, error)
        finally:
            self.alive = False
            for waiter in list(self._pending.values()):
                waiter['event'].set()

    def on(self, method, callback):
        self.handlers.setdefault(method, []).append(callback)

    def call(self, method, params=None, timeout=30):
        if not self.alive:
            raise CdpError('DevTools session %s is closed.' % self.name)
        with self._lock:
            self._id += 1
            call_id = self._id
        waiter = {'event': threading.Event(), 'result': None}
        self._pending[call_id] = waiter
        self.ws.send(json.dumps({'id': call_id, 'method': method, 'params': params or {}}))
        if not waiter['event'].wait(timeout):
            self._pending.pop(call_id, None)
            raise CdpError('%s timed out.' % method)
        result = waiter['result']
        if result is None:
            raise CdpError('DevTools session %s closed during %s.' % (self.name, method))
        if 'error' in result:
            raise CdpError('%s: %s' % (method, result['error'].get('message')))
        return result.get('result') or {}

    def close(self):
        self.alive = False
        self.ws.close()


def _http_json(path):
    with urllib.request.urlopen('http://%s:%s%s' % (HOST, PORT, path), timeout=5) as response:
        return json.loads(response.read().decode())


def browser_available():
    try:
        _http_json('/json/version')
        return True
    except OSError:
        return False


def connect_browser():
    return Session(_http_json('/json/version')['webSocketDebuggerUrl'], 'browser')


def page_targets():
    return [t for t in _http_json('/json/list') if t.get('type') == 'page']


def connect_page(target):
    return Session(target['webSocketDebuggerUrl'], target.get('id', 'page')[:8])

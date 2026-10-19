# -*- coding: utf-8 -*-
"""Signed requests between Odoo and the Raspberry Pis (bridges and displays).

A Pi is paired once with a one-time pairing code. Odoo then gives it a
secret key, which the Pi keeps. The key never travels with a request:
the Pi signs each one with HMAC-SHA256 over the method, path, a timestamp,
its MAC address, its device id and the body, and Odoo checks the signature
with its own copy of the key. Timestamps must be recent and always
increase, so a captured request can't be replayed. Odoo replaces the key
from time to time and hands the new one to the Pi in a signed response, so
the Pi never has to be paired again.

This file is shared: Odoo imports it to check requests and the Pi
programs import it (as embroidery_auth.py) to sign them, so it only uses
the Python standard library.
"""
import hashlib
import hmac
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HEADER_DEVICE = 'X-Embroidery-Device'
HEADER_TIMESTAMP = 'X-Embroidery-Timestamp'
HEADER_MAC = 'X-Embroidery-MAC'
HEADER_SIGNATURE = 'X-Embroidery-Signature'

# How far a Pi's clock may be from Odoo's.
MAX_CLOCK_SKEW_MS = 5 * 60 * 1000

PAIR_PATH = '/embroidery/pi/v1/pair'


# ─── Both sides ──────────────────────────────────────────────────────────────

def normalise_mac(value):
    """'B8-27-EB-12-34-56' -> 'b8:27:eb:12:34:56', or None if it isn't a MAC."""
    digits = re.sub(r'[^0-9a-fA-F]', '', value or '')
    if len(digits) != 12 or len(re.sub(r'[0-9a-fA-F:\-. ]', '', value or '')):
        return None
    return ':'.join(digits[i:i + 2] for i in range(0, 12, 2)).lower()


def parse_macs(text):
    """(set of valid MACs, list of entries that aren't MACs) in a free text list."""
    valid, invalid = set(), []
    for entry in re.split(r'[\s,;]+', text or ''):
        if not entry:
            continue
        mac = normalise_mac(entry)
        if mac:
            valid.add(mac)
        else:
            invalid.append(entry)
    return valid, invalid


def canonical_request(method, path, timestamp, mac, device, body):
    return '\n'.join([
        method.upper(),
        path,
        str(timestamp),
        mac or '',
        device,
        hashlib.sha256(body or b'').hexdigest(),
    ]).encode()


def sign(secret, method, path, timestamp, mac, device, body):
    message = canonical_request(method, path, timestamp, mac, device, body)
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify(secret, signature, method, path, timestamp, mac, device, body):
    expected = sign(secret, method, path, timestamp, mac, device, body)
    return hmac.compare_digest(expected, signature or '')


# ─── Pi side ─────────────────────────────────────────────────────────────────

def local_macs():
    """MAC addresses of this computer's network interfaces."""
    macs = []
    try:
        names = sorted(os.listdir('/sys/class/net'))
    except OSError:
        names = []
    for name in names:
        if name == 'lo':
            continue
        try:
            with open('/sys/class/net/%s/address' % name) as file:
                mac = normalise_mac(file.read().strip())
        except OSError:
            continue
        if mac and mac != '00:00:00:00:00:00' and mac not in macs:
            macs.append(mac)
    if not macs:
        node = uuid.getnode()
        macs.append(normalise_mac('%012x' % node))
    return macs


def primary_mac():
    """MAC of the interface the default route goes through (the one Odoo is reached by)."""
    try:
        with open('/proc/net/route') as file:
            for line in file.readlines()[1:]:
                fields = line.split()
                if len(fields) > 1 and fields[1] == '00000000':
                    with open('/sys/class/net/%s/address' % fields[0]) as address:
                        mac = normalise_mac(address.read().strip())
                    if mac:
                        return mac
    except OSError:
        pass
    return local_macs()[0]


class DeviceError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class Credentials:
    """The Pi's device id and secret key, kept in a file only its user can read."""

    def __init__(self, path):
        self.path = path
        self.data = {}
        if os.path.exists(path):
            with open(path, encoding='utf-8') as file:
                self.data = json.load(file)

    @property
    def paired(self):
        return bool(self.data.get('device') and self.data.get('secret'))

    def save(self):
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        tmp = self.path + '.new'
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(self.data, file, indent=4)
        os.replace(tmp, self.path)


class DeviceClient:
    """Makes signed requests to Odoo and keeps the key up to date."""

    def __init__(self, odoo_url, credentials_path, user_agent='EmbroideryPi', timeout=30):
        self.url = odoo_url.rstrip('/')
        self.credentials = Credentials(credentials_path)
        self.user_agent = user_agent
        self.timeout = timeout
        self.mac = primary_mac()
        self._lock = threading.Lock()
        self._last_ts = 0

    @property
    def paired(self):
        return self.credentials.paired

    def _timestamp(self):
        # Always increasing, even for requests made in the same millisecond.
        self._last_ts = max(int(time.time() * 1000), self._last_ts + 1)
        return self._last_ts

    def _open(self, request):
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()
        except (urllib.error.URLError, OSError) as error:
            raise DeviceError('%s: %s' % (request.full_url, error)) from None

    def pair(self, code, kind, version=''):
        """Exchange a one-time pairing code for this Pi's device id and key."""
        body = json.dumps({
            'code': code.strip(),
            'kind': kind,
            'mac': self.mac,
            'macs': local_macs(),
            'hostname': os.uname().nodename if hasattr(os, 'uname') else '',
            'version': version,
        }).encode()
        request = urllib.request.Request(self.url + PAIR_PATH, data=body, method='POST')
        request.add_header('Content-Type', 'application/json')
        request.add_header('User-Agent', self.user_agent)
        status, _headers, data = self._open(request)
        result = _json_or_message(data)
        if status != 200:
            raise DeviceError('Pairing failed: %s' % result.get('message', 'HTTP %s' % status), status)
        self.credentials.data = {
            'odoo_url': self.url,
            'kind': kind,
            'device': result['device'],
            'secret': result['secret'],
            'name': result.get('name', ''),
            'paired_mac': self.mac,
        }
        self.credentials.save()
        return result

    def request(self, method, path, payload=None, headers=None):
        """Signed request. Returns (status, headers, body bytes)."""
        if not self.paired:
            raise DeviceError('This Pi is not paired with Odoo yet.', 401)
        if payload is None:
            body = b''
        elif isinstance(payload, bytes):
            body = payload
        else:
            body = json.dumps(payload).encode()
        with self._lock:
            creds = self.credentials.data
            timestamp = self._timestamp()
            signature = sign(creds['secret'], method, path, timestamp, self.mac, creds['device'], body)
            request = urllib.request.Request(self.url + path, data=body if method != 'GET' else None,
                                             method=method)
            request.add_header(HEADER_DEVICE, creds['device'])
            request.add_header(HEADER_TIMESTAMP, str(timestamp))
            request.add_header(HEADER_MAC, self.mac)
            request.add_header(HEADER_SIGNATURE, signature)
            request.add_header('User-Agent', self.user_agent)
            if method != 'GET':
                request.add_header('Content-Type', 'application/json')
            for key, value in (headers or {}).items():
                request.add_header(key, value)
            # Sent while holding the lock so Odoo receives timestamps in order.
            return self._open(request)

    def request_json(self, method, path, payload=None):
        """Signed JSON request. Saves a replacement key if Odoo sends one."""
        status, _headers, data = self.request(method, path, payload)
        result = _json_or_message(data)
        if status != 200:
            raise DeviceError('%s %s: HTTP %s %s' % (method, path, status, result.get('message', '')), status)
        new_secret = result.pop('new_secret', None)
        if new_secret:
            self.accept_new_secret(new_secret)
        return result

    def accept_new_secret(self, secret):
        with self._lock:
            if self.credentials.data.get('secret') != secret:
                self.credentials.data['secret'] = secret
                self.credentials.save()


def _json_or_message(data):
    try:
        result = json.loads(data.decode() or '{}')
        return result if isinstance(result, dict) else {}
    except ValueError:
        return {'message': data[:200].decode(errors='replace')}


def path_of(url):
    """The path and query of a URL, as they are signed."""
    parts = urllib.parse.urlsplit(url)
    return parts.path + ('?' + parts.query if parts.query else '')

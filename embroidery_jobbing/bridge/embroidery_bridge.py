#!/usr/bin/env python3
"""Embroidery Bridge - connects Odoo's Embroidery Jobbing app to your machines.

Run it on a Raspberry Pi (or any computer with Python 3.8+) on the same
network as the embroidery machines; nothing else needs installing. Every few
seconds it asks Odoo for designs that were sent to its machines, delivers
them, and reports the stitch-out progress back to Odoo. It only makes
outgoing HTTPS requests, so nothing needs opening on the router.

On a Raspberry Pi, install.sh sets it up as a service that starts on boot
(Odoo shows the one-line install command when you generate the bridge's
access token). To run it by hand:

    python3 embroidery_bridge.py --config config.json

How a design reaches each machine is the machine's "Connection" in Odoo:

    folder     Save the .pes file into a folder: a USB stick plugged into
               the Pi (e.g. /media/*/* for whichever stick is mounted) or a
               shared network folder. Progress is then reported from Odoo
               by the operator.
    simulator  Pretend to stitch the design, reporting live progress,
               colour changes and a thread break, to try the whole flow
               before a machine is connected.

New drivers (e.g. one reading the machine's live status over the network)
subclass Driver and are added to DRIVERS.
"""
import argparse
import glob
import json
import logging
import os
import random
import re
import signal
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VERSION = '1.0.0'
API = '/embroidery/bridge/v1'
DEFAULT_POLL_SECONDS = 10
MAX_BACKOFF_SECONDS = 300

_logger = logging.getLogger('embroidery_bridge')


# ─── Odoo API ────────────────────────────────────────────────────────────────

class OdooError(Exception):
    pass


class Odoo:
    def __init__(self, url, token, timeout=30):
        self.url = url.rstrip('/')
        self.token = token
        self.timeout = timeout

    def _request(self, method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.url + path, data=data, method=method)
        request.add_header('Authorization', 'Bearer %s' % self.token)
        request.add_header('User-Agent', 'EmbroideryBridge/%s' % VERSION)
        if data is not None:
            request.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            body = error.read().decode(errors='replace')
            try:
                message = json.loads(body).get('message') or body
            except ValueError:
                message = body[:200]
            raise OdooError('%s %s: HTTP %s %s' % (method, path, error.code, message)) from None
        except (urllib.error.URLError, OSError) as error:
            raise OdooError('%s %s: %s' % (method, path, error)) from None

    def poll(self, machines):
        return json.loads(self._request('POST', API + '/poll', {'version': VERSION, 'machines': machines}))

    def download(self, path):
        return self._request('GET', path)

    def report(self, stitchout_id, payload):
        return json.loads(self._request('POST', '%s/stitchout/%s/report' % (API, stitchout_id), payload))


# ─── Drivers ─────────────────────────────────────────────────────────────────

class Driver:
    """Delivers designs to one machine and reports what it is doing."""

    def __init__(self, machine, settings):
        self.machine = machine          # the machine's settings from Odoo
        self.settings = settings        # this driver's section of config.json

    def configure(self, machine):
        self.machine = machine

    def status(self):
        """(online, message) for the machine."""
        return True, ''

    def deliver(self, job, data):
        """Get the design onto the machine. Return a message for the log."""
        raise NotImplementedError

    def forget(self, stitchout_id):
        """Odoo finished or cancelled the stitch out: stop looking after it."""

    def tick(self):
        """Progress reports to send: a list of (stitchout_id, report)."""
        return []


def safe_filename(name):
    # Letters, digits, - and _ only: some machines don't show other characters.
    name = re.sub(r'[^\w\-]+', '_', name).strip('_')
    return name[:60] or 'design'


class FolderDriver(Driver):
    """Saves the .pes file into a folder (USB stick, shared network folder).

    The folder may be a pattern such as /media/*/* : the first folder that
    matches is used, so any USB stick the Pi mounts there will do.
    """

    @property
    def pattern(self):
        return (self.machine.get('drop_folder') or self.settings.get('folder') or '').strip()

    @property
    def folder(self):
        pattern = os.path.expanduser(self.pattern)
        if glob.has_magic(pattern):
            matches = sorted(m for m in glob.glob(pattern) if os.path.isdir(m))
            return Path(matches[0]) if matches else None
        return Path(pattern) if pattern else None

    def status(self):
        if not self.pattern:
            return False, 'No folder set on the machine in Odoo'
        folder = self.folder
        if folder is None:
            return False, 'Nothing mounted at %s - is the USB stick plugged in?' % self.pattern
        if not folder.is_dir():
            return False, 'Folder not found: %s' % folder
        if not os.access(folder, os.W_OK):
            return False, 'Cannot write to %s' % folder
        return True, 'Saving designs to %s' % folder

    def deliver(self, job, data):
        online, message = self.status()
        if not online:
            raise OSError(message)
        stem = safe_filename('%s_%s' % (job['name'].replace('/', '-'), Path(job['filename']).stem))
        target = self.folder / (stem + '.pes')
        tmp = target.with_suffix('.part')
        tmp.write_bytes(data)
        os.replace(tmp, target)
        return 'Saved as %s' % target


class SimulatorDriver(Driver):
    """Pretends to stitch each design, reporting live progress."""

    def __init__(self, machine, settings):
        super().__init__(machine, settings)
        self.runs = {}

    def status(self):
        return True, 'Simulator ready'

    def deliver(self, job, data):
        speedup = float(self.settings.get('speedup', 10))
        colors = job.get('colors') or [{'name': '', 'stitches': job['total_stitches']}]
        boundaries, total = [], 0
        for color in colors:
            total += color['stitches']
            boundaries.append(total)
        error_at = None
        if self.settings.get('thread_breaks', True) and job['total_stitches'] > 100:
            error_at = int(job['total_stitches'] * random.uniform(0.3, 0.7))
        self.runs[job['stitchout_id']] = {
            'job': job,
            'speedup': speedup,
            'boundaries': boundaries,
            'stitch': 0.0,
            'color': 1,
            'state': 'sent',
            'until': time.time() + 5 / speedup,   # operator hooping and pressing start
            'error_at': error_at,
            'last': time.time(),
            'reported': None,
        }
        return 'Simulator loaded %s (%s stitches)' % (job['design'], job['total_stitches'])

    def forget(self, stitchout_id):
        self.runs.pop(stitchout_id, None)

    def tick(self):
        reports = []
        now = time.time()
        speed = int(self.machine.get('speed_spm') or 800)
        change_seconds = float(self.machine.get('color_change_seconds') or 15)
        for stitchout_id, run in list(self.runs.items()):
            elapsed, run['last'] = now - run['last'], now
            total = run['job']['total_stitches']
            report = {}
            if run['state'] in ('sent', 'paused', 'error'):
                if now >= run['until']:
                    report['message'] = 'Rethreaded and resumed' if run['state'] == 'error' else None
                    run['state'] = 'stitching'
            elif run['state'] == 'stitching' and now >= run['until']:
                run['stitch'] = min(run['stitch'] + speed / 60.0 * elapsed * run['speedup'], total)
                if run['error_at'] and run['stitch'] >= run['error_at']:
                    run['stitch'] = run['error_at']
                    run['error_at'] = None
                    run['state'] = 'error'
                    run['until'] = now + 20 / run['speedup']
                    report.update(message='Upper thread break', error_code='SIM-THREAD')
                else:
                    color = next((n for n, end in enumerate(run['boundaries'], 1) if run['stitch'] < end),
                                 len(run['boundaries']))
                    if color != run['color']:
                        run['color'] = color
                        run['until'] = now + change_seconds / run['speedup']
                    if run['stitch'] >= total:
                        run['state'] = 'done'
            report.update(status=run['state'], stitch=int(run['stitch']), color=run['color'],
                          speed=speed if run['state'] == 'stitching' else 0)
            report = {key: value for key, value in report.items() if value is not None}
            if report != run['reported']:
                reports.append((stitchout_id, report))
                run['reported'] = report
            if run['state'] == 'done':
                del self.runs[stitchout_id]
        return reports


DRIVERS = {
    'folder': FolderDriver,
    'simulator': SimulatorDriver,
}


# ─── Bridge ──────────────────────────────────────────────────────────────────

class Bridge:
    def __init__(self, config):
        self.config = config
        self.odoo = Odoo(config['odoo_url'], config['token'], timeout=config.get('timeout', 30))
        self.drivers = {}        # machine id -> Driver
        self.delivered = {}      # stitchout id -> machine id
        self.failed = {}         # stitchout id -> last delivery error reported

    def _driver_settings(self, name):
        return (self.config.get('drivers') or {}).get(name) or {}

    def _sync_machines(self, machines):
        seen = set()
        for machine in machines:
            seen.add(machine['id'])
            driver_class = DRIVERS.get(machine['driver'])
            driver = self.drivers.get(machine['id'])
            if driver_class is None:
                self.drivers.pop(machine['id'], None)
                continue
            if driver is None or type(driver) is not driver_class:
                _logger.info('Machine %s uses the %s driver', machine['name'], machine['driver'])
                self.drivers[machine['id']] = driver_class(machine, self._driver_settings(machine['driver']))
            else:
                driver.configure(machine)
        for machine_id in set(self.drivers) - seen:
            del self.drivers[machine_id]

    def _machine_statuses(self):
        statuses = []
        for machine_id, driver in self.drivers.items():
            try:
                online, message = driver.status()
            except Exception as error:  # a broken driver must not stop the others
                online, message = False, str(error)
            statuses.append({'id': machine_id, 'online': online, 'message': message})
        return statuses

    def _report(self, stitchout_id, report):
        try:
            self.odoo.report(stitchout_id, report)
        except OdooError as error:
            _logger.warning('Could not report stitch out %s: %s', stitchout_id, error)

    def _deliver(self, job):
        driver = self.drivers.get(job['machine_id'])
        if driver is None or job['stitchout_id'] in self.delivered:
            return
        try:
            data = self.odoo.download(job['file_url'])
            message = driver.deliver(job, data)
        except Exception as error:
            text = 'Could not deliver the design: %s' % error
            _logger.warning('%s: %s', job['name'], text)
            if self.failed.get(job['stitchout_id']) != text:
                # Logged once; delivery is retried on every poll while queued.
                self.failed[job['stitchout_id']] = text
                self._report(job['stitchout_id'], {'events': [{'type': 'info', 'message': text}]})
            return
        _logger.info('%s: %s', job['name'], message)
        self.failed.pop(job['stitchout_id'], None)
        self.delivered[job['stitchout_id']] = job['machine_id']
        self._report(job['stitchout_id'], {'status': 'sent', 'message': message})

    def run_once(self):
        response = self.odoo.poll(self._machine_statuses())
        self._sync_machines(response.get('machines') or [])
        open_stitchouts = response.get('open') or {}
        for stitchout_id, machine_id in list(self.delivered.items()):
            if str(stitchout_id) not in open_stitchouts:
                del self.delivered[stitchout_id]
                driver = self.drivers.get(machine_id)
                if driver:
                    driver.forget(stitchout_id)
        for job in response.get('queued') or []:
            self._deliver(job)
        for driver in list(self.drivers.values()):
            for stitchout_id, report in driver.tick():
                self._report(stitchout_id, report)
        return response.get('poll_seconds') or self.config.get('poll_seconds', DEFAULT_POLL_SECONDS)

    def run_forever(self):
        _logger.info('Embroidery Bridge %s connecting to %s', VERSION, self.odoo.url)
        backoff = 0
        while True:
            try:
                wait = self.run_once()
                if backoff:
                    _logger.info('Connected to Odoo again')
                backoff = 0
                if any(isinstance(d, SimulatorDriver) and d.runs for d in self.drivers.values()):
                    wait = min(wait, 2)
            except OdooError as error:
                backoff = min(max(backoff * 2, 5), MAX_BACKOFF_SECONDS)
                _logger.warning('%s - retrying in %ss', error, backoff)
                wait = backoff
            time.sleep(wait)


def load_config(path):
    with open(path, encoding='utf-8') as file:
        config = json.load(file)
    missing = [key for key in ('odoo_url', 'token') if not config.get(key)]
    if missing:
        raise SystemExit('%s is missing: %s' % (path, ', '.join(missing)))
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--config', default=str(Path(__file__).with_name('config.json')),
                        help='config file (default: config.json beside this script)')
    parser.add_argument('--once', action='store_true', help='poll Odoo once and exit')
    parser.add_argument('--verbose', action='store_true', help='log more detail')
    args = parser.parse_args(argv)
    config = load_config(args.config)
    handlers = [logging.StreamHandler(sys.stdout)]
    if config.get('log_file'):
        handlers.append(logging.FileHandler(config['log_file'], encoding='utf-8'))
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', datefmt='%d/%m/%Y %H:%M:%S',
                        handlers=handlers)
    # systemd stops the service with SIGTERM.
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    bridge = Bridge(config)
    if args.once:
        bridge.run_once()
        return
    try:
        bridge.run_forever()
    except (KeyboardInterrupt, SystemExit):
        _logger.info('Stopped')


if __name__ == '__main__':
    main()

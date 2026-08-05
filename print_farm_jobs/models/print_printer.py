import hashlib
import json
import logging
import ssl
import ftplib
import io
import base64
import threading

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


PRINTER_MODEL_SELECTION = [
    ('bambu_x1c', 'Bambu Lab X1 Carbon'),
    ('bambu_x1e', 'Bambu Lab X1E'),
    ('bambu_p1s', 'Bambu Lab P1S'),
    ('bambu_p1p', 'Bambu Lab P1P'),
    ('bambu_a1', 'Bambu Lab A1'),
    ('bambu_a1_mini', 'Bambu Lab A1 Mini'),
    ('bambu_h2d', 'Bambu Lab H2D'),
    ('other', 'Other / Generic'),
]

PRINTER_STATE_SELECTION = [
    ('idle', 'Idle'),
    ('printing', 'Printing'),
    ('paused', 'Paused'),
    ('error', 'Error'),
    ('offline', 'Offline'),
    ('unknown', 'Unknown'),
]


class PrintPrinterFilamentSlot(models.Model):
    _name = 'print.printer.filament.slot'
    _description = 'Printer Filament Slot'
    _order = 'ams_unit, slot_number'

    printer_id = fields.Many2one(
        'print.printer',
        string='Printer',
        required=True,
        ondelete='cascade',
    )
    ams_unit = fields.Integer(
        string='AMS Unit',
        default=1,
        help='AMS unit number (1 = first AMS). Use 0 for direct spool (no AMS).',
    )
    slot_number = fields.Integer(
        string='Slot',
        default=1,
        help='Slot number within the AMS unit (1-4), or 1 for direct spool.',
    )
    slot_label = fields.Char(
        string='Slot Label',
        compute='_compute_slot_label',
        store=True,
    )
    filament_id = fields.Many2one(
        'print.filament',
        string='Filament Type',
        help='Filament type loaded in this slot (set automatically when a spool is assigned)',
    )
    spool_id = fields.Many2one(
        'print.filament.spool',
        string='Loaded Spool',
        help='Specific spool currently loaded in this slot',
        domain="[('state', 'in', ['new', 'in_use'])]",
    )
    is_loaded = fields.Boolean(
        string='Loaded',
        default=True,
        help='Whether filament is currently loaded in this slot',
    )
    remaining_weight_g = fields.Float(
        string='Remaining (g)',
        compute='_compute_remaining',
        store=True,
        help='Remaining filament on the loaded spool',
    )
    color_hex = fields.Char(
        related='filament_id.color_hex',
        string='Colour',
    )

    @api.depends('spool_id.weight_remaining_g')
    def _compute_remaining(self):
        for rec in self:
            rec.remaining_weight_g = rec.spool_id.weight_remaining_g if rec.spool_id else 0.0

    @api.onchange('spool_id')
    def _onchange_spool_id(self):
        """Live UI feedback only — filament_id is persisted server-side in create/write."""
        if self.spool_id:
            self.filament_id = self.spool_id.filament_id
            self.is_loaded = True

    def _sync_filament_from_spool(self, vals):
        """If spool_id is being set, inject the matching filament_id into vals."""
        spool_id = vals.get('spool_id')
        if spool_id:
            spool = self.env['print.filament.spool'].browse(spool_id)
            if spool.filament_id:
                vals['filament_id'] = spool.filament_id.id
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sync_filament_from_spool(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._sync_filament_from_spool(vals)
        return super().write(vals)

    @api.depends('ams_unit', 'slot_number')
    def _compute_slot_label(self):
        for rec in self:
            if rec.ams_unit == 0:
                rec.slot_label = 'Direct Spool'
            else:
                rec.slot_label = 'AMS %d · Slot %d' % (rec.ams_unit, rec.slot_number)


class PrintPrinter(models.Model):
    _name = 'print.printer'
    _description = '3D Printer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # ── Identity ─────────────────────────────────────────────────────────────
    name = fields.Char(string='Printer Name', required=True, tracking=True)
    printer_model = fields.Selection(
        PRINTER_MODEL_SELECTION,
        string='Model',
        default='bambu_x1c',
        required=True,
        tracking=True,
    )
    serial_number = fields.Char(string='Serial Number', tracking=True)
    location = fields.Char(string='Location / Bay', help='Physical location in the print farm')
    notes = fields.Text(string='Notes')
    active = fields.Boolean(default=True)

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        PRINTER_STATE_SELECTION,
        string='Status',
        default='unknown',
        readonly=True,
    )
    last_status_check = fields.Datetime(string='Last Status Check', readonly=True)
    current_job_id = fields.Many2one(
        'print.job',
        string='Current Job',
        readonly=True,
    )

    # ── Connection – Local LAN ────────────────────────────────────────────────
    local_ip = fields.Char(
        string='Printer IP Address',
        help='Local IP address of the printer on your LAN',
    )
    access_code = fields.Char(
        string='Access Code',
        help='Access code shown on the printer screen (LAN mode)',
    )
    local_ftp_port = fields.Char(
        string='FTP Port',
        default='990',
        help='FTPS port for file upload (default 990)',
    )
    local_mqtt_port = fields.Char(
        string='MQTT Port',
        default='8883',
        help='MQTT port for print commands (default 8883)',
    )

    # ── Print Farm Agent (bridges Odoo.sh → local LAN) ───────────────────────
    agent_url = fields.Char(
        string='Agent URL',
        help=(
            'Public HTTPS URL of the local Print Farm Agent.\n'
            'Example: https://mypc.tailnet.ts.net\n'
            'Leave blank when Odoo runs on the same LAN as the printer.'
        ),
    )
    agent_api_key = fields.Char(
        string='Agent API Key',
        help='Secret key configured on the local agent (AGENT_API_KEY env var).',
    )

    # ── Filament Slots ─────────────────────────────────────────────────────────
    filament_slot_ids = fields.One2many(
        'print.printer.filament.slot',
        'printer_id',
        string='Filament Slots',
    )
    loaded_filament_ids = fields.Many2many(
        'print.filament',
        compute='_compute_loaded_filaments',
        string='Loaded Filaments',
    )
    slot_count = fields.Integer(
        string='Slots',
        compute='_compute_slot_count',
    )

    # ── Statistics ────────────────────────────────────────────────────────────
    job_ids = fields.One2many('print.job', 'printer_id', string='Jobs')
    job_count = fields.Integer(compute='_compute_job_count', string='Total Jobs')
    queued_job_count = fields.Integer(compute='_compute_job_count', string='Queued Jobs')

    # ─────────────────────────────────────────────────────────────────────────
    # Computed fields
    # ─────────────────────────────────────────────────────────────────────────

    @api.depends('filament_slot_ids.filament_id', 'filament_slot_ids.is_loaded')
    def _compute_loaded_filaments(self):
        for rec in self:
            rec.loaded_filament_ids = rec.filament_slot_ids.filtered('is_loaded').mapped('filament_id')

    @api.depends('filament_slot_ids')
    def _compute_slot_count(self):
        for rec in self:
            rec.slot_count = len(rec.filament_slot_ids)

    @api.depends('job_ids.state')
    def _compute_job_count(self):
        for rec in self:
            rec.job_count = len(rec.job_ids)
            rec.queued_job_count = len(rec.job_ids.filtered(lambda j: j.state == 'queued'))

    # ─────────────────────────────────────────────────────────────────────────
    # Filament capability check
    # ─────────────────────────────────────────────────────────────────────────

    def _ftp_port(self):
        """Return the FTP port as an integer, falling back to 990."""
        try:
            return int(self.local_ftp_port or 990)
        except (ValueError, TypeError):
            return 990

    def _mqtt_port(self):
        """Return the MQTT port as an integer, falling back to 8883."""
        try:
            return int(self.local_mqtt_port or 8883)
        except (ValueError, TypeError):
            return 8883

    def can_print_job(self, job):
        """Return True if this printer has all filaments required by the job loaded."""
        self.ensure_one()
        required = job.required_filament_ids.mapped('filament_id')
        loaded = self.loaded_filament_ids
        return all(f in loaded for f in required)

    # ─────────────────────────────────────────────────────────────────────────
    # API – Print Farm Agent (remote proxy for Odoo.sh → LAN)
    # ─────────────────────────────────────────────────────────────────────────

    def _agent_request(self, path, payload):
        """POST to the local agent and return the JSON response dict.

        Raises UserError on network failure or non-2xx response.
        """
        self.ensure_one()
        try:
            import requests as _requests
        except ImportError:
            raise UserError(_('The "requests" Python package is required.'))

        url = '%s%s' % (self.agent_url.rstrip('/'), path)
        try:
            resp = _requests.post(
                url,
                json=payload,
                headers={'X-Api-Key': self.agent_api_key or ''},
                timeout=120,
            )
        except Exception as e:
            raise UserError(
                _('Could not reach the Print Farm Agent at %s.\n'
                  'Check the Agent URL and that the agent is running.\n'
                  'Details: %s') % (url, str(e))
            )

        if resp.status_code == 401:
            raise UserError(
                _('Print Farm Agent rejected the request (wrong API key).\n'
                  'Check the Agent API Key on the printer matches the '
                  'AGENT_API_KEY set on the agent machine.')
            )
        if not resp.ok:
            raise UserError(
                _('Print Farm Agent returned an error (HTTP %s): %s')
                % (resp.status_code, resp.text[:300])
            )
        return resp.json()

    def _agent_send_job(self, job):
        """Upload file and send print command via the local agent."""
        self.ensure_one()
        if not self.serial_number:
            raise UserError(
                _('Printer "%s" has no Serial Number — required for MQTT.') % self.name
            )
        if not job.job_file:
            raise UserError(_('Job "%s" has no file attached.') % job.name)

        filename = job.job_filename or ('%s.3mf' % job.name)

        # Build AMS mapping from loaded slots
        loaded_slots = self.filament_slot_ids.filtered('is_loaded')
        if loaded_slots and job.use_ams:
            ams_mapping = [max(0, s.slot_number - 1) for s in loaded_slots]
        else:
            ams_mapping = [0]

        result = self._agent_request('/print', {
            'ip':            self.local_ip,
            'access_code':   self.access_code,
            'serial_number': self.serial_number,
            'ftp_port':      self._ftp_port(),
            'mqtt_port':     self._mqtt_port(),
            'filename':      filename,
            'file_b64':      job.job_file.decode() if isinstance(job.job_file, bytes) else job.job_file,
            'settings': {
                'plate_number':         job.plate_number or 1,
                'use_ams':              job.use_ams,
                'bed_leveling':         job.bed_leveling,
                'flow_calibration':     job.flow_calibration,
                'vibration_calibration': job.vibration_calibration,
                'layer_inspect':        job.layer_inspect,
                'timelapse':            job.timelapse,
                'ams_mapping':          ams_mapping,
            },
        })

        if result.get('status') != 'ok':
            raise UserError(
                _('Print Farm Agent failed to send job: %s') % result.get('error', 'Unknown error')
            )

    def _agent_check_status(self):
        """Fetch printer state from the local agent."""
        self.ensure_one()
        result = self._agent_request('/status', {
            'ip':          self.local_ip,
            'access_code': self.access_code,
            'serial':      self.serial_number or '',
            'mqtt_port':   self._mqtt_port(),
        })
        raw = result.get('state', 'UNKNOWN').upper()
        GCODE_STATE_MAP = {
            'IDLE':    'idle',
            'FINISH':  'idle',
            'RUNNING': 'printing',
            'PAUSE':   'paused',
            'FAILED':  'error',
            'SLICING': 'printing',
            'PREPARE': 'printing',
        }
        return GCODE_STATE_MAP.get(raw, 'unknown')

    # ─────────────────────────────────────────────────────────────────────────
    # API – Local FTPS file upload
    # ─────────────────────────────────────────────────────────────────────────

    def _ftps_upload_file(self, file_content_b64, remote_filename):
        """Upload a file to the printer's local FTPS server.

        Returns the remote path on success, raises UserError on failure.
        """
        self.ensure_one()
        if not self.local_ip:
            raise UserError(_('Printer "%s" has no IP address configured.') % self.name)
        if not self.access_code:
            raise UserError(_('Printer "%s" has no Access Code configured.') % self.name)

        file_bytes = base64.b64decode(file_content_b64)
        remote_path = '/cache/%s' % remote_filename
        host = self.local_ip
        port = self._ftp_port()

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # Bambu uses self-signed cert

        import socket as _socket

        # Bambu printers use IMPLICIT TLS on port 990 — TLS must be negotiated
        # immediately after TCP connect, before any FTP protocol bytes are sent.
        # Python's FTP_TLS uses *explicit* TLS (sends AUTH TLS over a plain
        # channel first), which causes a 30-second deadlock because the printer
        # is waiting for a TLS ClientHello and Python is waiting for the FTP
        # "220" banner.  The fix is to wrap the socket in TLS ourselves right
        # after the TCP handshake, then inject it into a plain FTP instance.
        try:
            _logger.info('FTPS [%s]: TCP connecting to %s:%s', self.name, host, port)
            raw_sock = _socket.create_connection((host, port), timeout=30)
            raw_sock.settimeout(30)

            _logger.info('FTPS [%s]: TLS handshake (implicit)', self.name)
            ssl_sock = ctx.wrap_socket(raw_sock)
            ssl_sock.settimeout(30)

            # Inject the live SSL socket into a plain FTP client
            ftp = ftplib.FTP()
            ftp.sock = ssl_sock
            ftp.af   = ssl_sock.family
            ftp.file = ssl_sock.makefile('r', encoding='utf-8')
            ftp.welcome = ftp.getresp()   # read the "220 ..." banner
            _logger.info('FTPS [%s]: connected – %s', self.name, ftp.welcome.strip())

            ftp.login('bblp', self.access_code)
            _logger.info('FTPS [%s]: authenticated', self.name)

            ftp.set_pasv(True)
            _logger.info('FTPS [%s]: uploading %s (%d bytes) → %s',
                         self.name, remote_filename, len(file_bytes), remote_path)
            ftp.storbinary('STOR %s' % remote_path, io.BytesIO(file_bytes))
            _logger.info('FTPS [%s]: upload complete', self.name)
            try:
                ftp.quit()
            except Exception:
                ftp.close()

        except _socket.timeout:
            raise UserError(_(
                'Cannot reach printer "%s" at %s:%s — connection timed out.\n\n'
                'Check that the IP address is correct and the printer is '
                'on the same network as this server.'
            ) % (self.name, host, port))
        except ssl.SSLError as e:
            raise UserError(_(
                'TLS handshake with printer "%s" failed: %s\n\n'
                'Ensure LAN Mode and Developer Mode are both enabled on the printer.'
            ) % (self.name, str(e)))
        except ftplib.error_perm as e:
            raise UserError(_(
                'FTPS login to printer "%s" was rejected: %s\n\n'
                'Check that the Access Code matches the code shown on the printer screen.'
            ) % (self.name, str(e)))
        except ftplib.all_errors as e:
            raise UserError(
                _('FTPS upload to printer "%s" failed: %s') % (self.name, str(e))
            )

        return remote_path

    # ─────────────────────────────────────────────────────────────────────────
    # API – Local MQTT print command
    # ─────────────────────────────────────────────────────────────────────────

    def _mqtt_send_print_command(self, remote_path, job):
        """Send a project_file print command via local MQTT (paho-mqtt 2.x)."""
        self.ensure_one()
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise UserError(
                _('The paho-mqtt Python package is required for local MQTT control.\n'
                  'Install it with: pip install paho-mqtt')
            )

        if not self.serial_number:
            raise UserError(
                _('Printer "%s" has no Serial Number configured. '
                  'The serial number is required to address MQTT commands.') % self.name
            )
        if not self.local_ip:
            raise UserError(_('Printer "%s" has no IP address configured.') % self.name)
        if not self.access_code:
            raise UserError(_('Printer "%s" has no Access Code configured.') % self.name)

        topic = 'device/%s/request' % self.serial_number
        filename = remote_path.split('/')[-1]

        # Compute MD5 of the file (required by Bambu firmware)
        file_bytes = base64.b64decode(job.job_file)
        file_md5 = hashlib.md5(file_bytes).hexdigest()

        plate = job.plate_number or 1

        # AMS mapping: list of 0-based tray indices for each loaded slot
        loaded_slots = self.filament_slot_ids.filtered('is_loaded')
        if loaded_slots and job.use_ams:
            ams_mapping = [max(0, s.slot_number - 1) for s in loaded_slots]
        else:
            ams_mapping = [0]

        payload = json.dumps({
            'print': {
                'sequence_id': str(int(fields.Datetime.now().timestamp())),
                'command': 'project_file',
                'param': 'Metadata/plate_%d.gcode' % plate,
                'file': filename,
                'url': 'ftp:///cache/%s' % filename,
                'md5': file_md5,
                'bed_type': 'auto',
                'timelapse': job.timelapse,
                'bed_leveling': job.bed_leveling,
                'flow_cali': job.flow_calibration,
                'vibration_cali': job.vibration_calibration,
                'layer_inspect': job.layer_inspect,
                'use_ams': job.use_ams,
                'ams_mapping': ams_mapping,
                'subtask_name': filename,
                'profile_id': '0',
                'project_id': '0',
                'subtask_id': '0',
                'task_id': '0',
            }
        })

        connected = threading.Event()
        published = threading.Event()
        connect_failed = []

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code.is_failure:
                _logger.warning('Local MQTT connect failed for %s: %s', self.name, reason_code)
                connect_failed.append(str(reason_code))
            connected.set()

        def on_publish(client, userdata, mid, reason_code=None, properties=None):
            published.set()

        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE  # Bambu uses a self-signed certificate

            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id='odoo_print_%s' % self.id,
            )
            client.username_pw_set('bblp', self.access_code)
            client.tls_set_context(ctx)
            client.on_connect = on_connect
            client.on_publish = on_publish
            client.connect(self.local_ip, self._mqtt_port(), keepalive=15)
            client.loop_start()

            if not connected.wait(timeout=15):
                client.loop_stop()
                raise UserError(
                    _('Timed out connecting to printer "%s" via local MQTT. '
                      'Check the IP address and that the printer is online.') % self.name
                )

            if connect_failed:
                client.loop_stop()
                raise UserError(
                    _('Failed to connect to printer "%s" via local MQTT: %s\n'
                      'Check the Access Code and that Developer Mode is enabled on the printer.')
                    % (self.name, connect_failed[0])
                )

            result = client.publish(topic, payload, qos=1)
            if not published.wait(timeout=15):
                client.loop_stop()
                raise UserError(
                    _('Timed out waiting for MQTT publish confirmation for printer "%s".')
                    % self.name
                )
            client.loop_stop()
            try:
                client.disconnect()
            except Exception:
                pass

        except UserError:
            raise
        except Exception as e:
            raise UserError(
                _('MQTT command to printer "%s" failed: %s') % (self.name, str(e))
            )

        if result.rc != 0:
            raise UserError(
                _('MQTT publish failed for printer "%s" (rc=%s).') % (self.name, result.rc)
            )

        _logger.info(
            'Local MQTT print command sent to printer %s (file=%s, md5=%s)',
            self.name, filename, file_md5,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # API – Local MQTT status check
    # ─────────────────────────────────────────────────────────────────────────

    def _local_mqtt_get_state(self):
        """Subscribe to the printer's local MQTT report topic, send a pushall
        command, and return the mapped Odoo state string, or None on failure."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            _logger.warning('paho-mqtt not available – skipping local MQTT status check')
            return None

        if not self.local_ip or not self.access_code or not self.serial_number:
            return None

        GCODE_STATE_MAP = {
            'IDLE':    'idle',
            'FINISH':  'idle',
            'RUNNING': 'printing',
            'PAUSE':   'paused',
            'FAILED':  'error',
            'SLICING': 'printing',
            'PREPARE': 'printing',
        }

        report_topic  = 'device/%s/report'  % self.serial_number
        request_topic = 'device/%s/request' % self.serial_number

        result       = {'state': None}
        done         = threading.Event()
        # Only process messages received *after* pushall has been sent,
        # to avoid acting on stale retained messages.
        pushall_sent = threading.Event()

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code.is_failure:
                _logger.warning(
                    'Local MQTT connect failed for %s: %s', self.name, reason_code
                )
                done.set()
                return
            # Subscribe first; publish pushall only after SUBACK (on_subscribe)
            client.subscribe(report_topic, qos=1)

        def on_subscribe(client, userdata, mid, reason_codes, properties):
            # SUBACK received – subscription is live; safe to request status
            client.publish(request_topic, json.dumps({
                'pushing': {'command': 'pushall'},
                'info':    {'command': 'get_version'},
            }), qos=1)
            pushall_sent.set()

        def on_message(client, userdata, msg):
            try:
                if not pushall_sent.is_set():
                    _logger.debug('Ignoring pre-pushall MQTT message for %s', self.name)
                    return
                data = json.loads(msg.payload.decode())
                raw = data.get('print', {}).get('gcode_state', '')
                _logger.info('Local MQTT state for %s: gcode_state=%r', self.name, raw)
                if not raw:
                    return
                result['state'] = GCODE_STATE_MAP.get(raw.upper(), 'unknown')
                done.set()
                try:
                    client.disconnect()
                except Exception:
                    pass
            except Exception as e:
                _logger.warning('Failed to parse local MQTT message for %s: %s', self.name, e)

        def on_disconnect(client, userdata, flags, reason_code, properties):
            done.set()

        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id='odoo_status_%s' % self.id,
            )
            client.username_pw_set('bblp', self.access_code)
            client.tls_set_context(ctx)
            client.on_connect    = on_connect
            client.on_subscribe  = on_subscribe
            client.on_message    = on_message
            client.on_disconnect = on_disconnect
            client.connect(self.local_ip, self._mqtt_port(), keepalive=15)
            client.loop_start()
            done.wait(timeout=20)
            client.loop_stop()
            try:
                client.disconnect()
            except Exception:
                pass
        except Exception as e:
            _logger.warning('Local MQTT status check failed for %s: %s', self.name, e)

        return result['state']

    def _local_check_status(self):
        """Update printer state — routes through agent when configured."""
        self.ensure_one()
        import socket as _socket

        if not self.local_ip:
            self.state = 'unknown'
            return

        # ── Route through agent when Odoo can't reach the printer directly ───
        if self.agent_url:
            try:
                self.state = self._agent_check_status()
            except Exception as e:
                _logger.warning('Agent status check failed for %s: %s', self.name, e)
                self.state = 'unknown'
            return

        # ── Step 1: TCP reachability on the MQTT port ─────────────────────────
        mqtt_port = self._mqtt_port()
        try:
            s = _socket.create_connection((self.local_ip, mqtt_port), timeout=5)
            s.close()
            _logger.info('Printer %s reachable at %s:%s', self.name, self.local_ip, mqtt_port)
        except Exception as e:
            _logger.warning(
                'Printer %s not reachable at %s:%s — %s',
                self.name, self.local_ip, mqtt_port, e,
            )
            self.state = 'offline'
            return

        # ── Step 2: MQTT pushall for exact state ──────────────────────────────
        if self.serial_number and self.access_code:
            state = self._local_mqtt_get_state()
            if state is not None:
                self.state = state
                return
            _logger.warning(
                'Printer %s: MQTT pushall returned no state '
                '(serial=%s). Printer is reachable — check the serial number '
                'is correct (Settings → Device on the printer touchscreen).',
                self.name, self.serial_number,
            )
        else:
            _logger.warning(
                'Printer %s: serial number or access code not configured — '
                'cannot read exact state via MQTT.',
                self.name,
            )

        # ── Step 3: Printer is online but state is unknown ────────────────────
        # We reached the printer over TCP so it is definitely not offline.
        if self.state in ('unknown', 'offline'):
            self.state = 'idle'

    # ─────────────────────────────────────────────────────────────────────────
    # Public action: check status
    # ─────────────────────────────────────────────────────────────────────────

    def action_check_status(self):
        """Attempt to reach the printer and update its status."""
        for printer in self:
            try:
                printer._local_check_status()
            except UserError:
                raise
            except Exception:
                printer.state = 'offline'
            printer.last_status_check = fields.Datetime.now()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Status Updated'),
                'message': _('Printer status has been refreshed.'),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    @api.model
    def _cron_check_all_printer_status(self):
        """Scheduled action: refresh the status of every active printer."""
        printers = self.search([('active', '=', True)])
        for printer in printers:
            try:
                printer._local_check_status()
            except Exception as e:
                _logger.warning(
                    'Cron status check failed for printer %s: %s', printer.name, e
                )
                printer.state = 'offline'
            printer.last_status_check = fields.Datetime.now()

    def action_view_jobs(self):
        self.ensure_one()
        return {
            'name': _('Jobs – %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'print.job',
            'view_mode': 'list,form',
            'domain': [('printer_id', '=', self.id)],
            'context': {'default_printer_id': self.id},
        }

    # ─────────────────────────────────────────────────────────────────────────
    # API – Cached file management (list / delete via agent)
    # ─────────────────────────────────────────────────────────────────────────

    def _agent_list_files(self):
        """Return a list of dicts with 'name' and 'size' for each file in /cache/."""
        self.ensure_one()
        result = self._agent_request('/files', {
            'ip':          self.local_ip,
            'access_code': self.access_code,
            'ftp_port':    self._ftp_port(),
        })
        return result.get('files', [])

    def _agent_delete_file(self, filename):
        """Delete a single file from the printer's /cache/ directory."""
        self.ensure_one()
        self._agent_request('/files/delete', {
            'ip':          self.local_ip,
            'access_code': self.access_code,
            'ftp_port':    self._ftp_port(),
            'filename':    filename,
        })

    def action_manage_files(self):
        """Open the cached-files wizard for this printer."""
        self.ensure_one()
        if not self.agent_url:
            raise UserError(
                _('Printer "%s" has no Agent URL configured.') % self.name
            )
        wizard = self.env['print.printer.file.wizard'].create({
            'printer_id': self.id,
        })
        wizard.action_refresh()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'print.printer.file.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

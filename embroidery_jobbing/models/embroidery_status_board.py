# -*- coding: utf-8 -*-
import shlex
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.addons.base.models.res_partner import _tz_get

from .embroidery_stitchout import format_duration

# Layouts and themes are built into the status page's code.
LAYOUT_SELECTION = [
    ('grid', 'Grid of machine cards'),
    ('list', 'List, one row per machine'),
    ('focus', 'One machine at a time (rotating)'),
]
THEME_SELECTION = [
    ('dark', 'Dark'),
    ('light', 'Light'),
]

# A display that hasn't asked for data for this long is shown as offline.
DISPLAY_OFFLINE_AFTER = timedelta(minutes=2)
# How often a display's "last seen" is written (it polls far more often).
DISPLAY_HEARTBEAT_EVERY = timedelta(seconds=30)


class EmbroideryStatusBoard(models.Model):
    """What a wall display shows about the machines, and how it is laid out."""
    _name = 'embroidery.status.board'
    _description = 'Embroidery Status Board'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    title = fields.Char(help='Heading at the top of the screen. Leave empty to use the board name.')
    machine_ids = fields.Many2many(
        'embroidery.machine', string='Machines',
        help='Machines on the board, in this order. Leave empty to show every active machine.',
    )
    display_ids = fields.One2many('embroidery.display', 'board_id', string='Displays')
    display_count = fields.Integer(compute='_compute_display_count')

    # ── Layout ────────────────────────────────────────────────────────────
    layout = fields.Selection(LAYOUT_SELECTION, required=True, default='grid')
    columns = fields.Integer(default=0, help='Machine cards per row in the grid. 0 picks a number that fits.')
    theme = fields.Selection(THEME_SELECTION, required=True, default='dark')
    font_scale = fields.Integer(string='Text Size (%)', default=100,
                                help='Make everything bigger or smaller, e.g. 150 for a TV across the room.')
    rotate_seconds = fields.Integer(string='Seconds per Machine', default=15,
                                    help='How long each machine is shown in the one-machine-at-a-time layout.')
    refresh_seconds = fields.Integer(string='Refresh Every (s)', default=5,
                                     help='How often the screen fetches the latest status.')
    tz = fields.Selection(_tz_get, string='Time Zone', required=True,
                          default=lambda self: self.env.user.tz or self.env.company.partner_id.tz or 'UTC',
                          help='Time zone of the clock and ETAs on the screen.')

    # ── What is shown ─────────────────────────────────────────────────────
    show_header = fields.Boolean(string='Heading', default=True)
    show_logo = fields.Boolean(string='Company Logo', default=True)
    show_clock = fields.Boolean(string='Clock and Date', default=True)
    show_summary = fields.Boolean(string='Status Summary', default=True,
                                  help='How many machines are stitching, waiting, idle, stopped or offline.')
    show_job = fields.Boolean(string='Current Job', default=True)
    show_customer = fields.Boolean(string='Customer', default=True)
    show_product = fields.Boolean(string='Product and Pieces', default=True)
    show_operator = fields.Boolean(string='Assigned To', default=False)
    show_preview = fields.Boolean(string='Design Preview', default=True)
    show_progress = fields.Boolean(string='Progress Bar', default=True)
    show_stitches = fields.Boolean(string='Stitch Count', default=True)
    show_colour = fields.Boolean(string='Current Thread Colour', default=True)
    show_eta = fields.Boolean(string='Time Remaining and ETA', default=True)
    show_errors = fields.Boolean(string='Errors', default=True)
    show_queue = fields.Boolean(string='Next Jobs', default=True,
                                help="The machine's next jobs waiting to be stitched.")
    queue_size = fields.Integer(string='Next Jobs Shown', default=3)
    show_offline = fields.Boolean(string='Offline Machines', default=True,
                                  help='Untick to leave machines whose bridge is offline off the screen.')

    _check_refresh = models.Constraint('CHECK(refresh_seconds >= 2)', 'Refresh at most every 2 seconds.')
    _check_font_scale = models.Constraint('CHECK(font_scale BETWEEN 50 AND 300)', 'Text size must be 50-300%.')

    def _compute_display_count(self):
        for board in self:
            board.display_count = len(board.display_ids)

    def _machines(self):
        self.ensure_one()
        machines = self.machine_ids.filtered('active') or self.env['embroidery.machine'].search([])
        if not self.show_offline:
            machines = machines.filtered(lambda m: m.status != 'offline')
        return machines

    def _format_time(self, value, now):
        """dd/mm/yyyy HH:MM, or just HH:MM today, in the board's time zone."""
        local = fields.Datetime.context_timestamp(self.with_context(tz=self.tz), value)
        today = fields.Datetime.context_timestamp(self.with_context(tz=self.tz), now).date()
        return local.strftime('%H:%M') if local.date() == today else local.strftime('%d/%m/%Y %H:%M')

    def _machine_data(self, machine, now, image_url):
        status_labels = dict(machine._fields['status']._description_selection(self.env))
        data = {
            'id': machine.id,
            'name': machine.name,
            'model': machine.machine_model_id.name or '',
            'status': machine.status,
            'status_label': status_labels.get(machine.status, ''),
            'message': machine.bridge_message or '' if machine.status == 'offline' else '',
            'job': None,
            'stitchout': None,
            'queue': [],
        }
        stitchout = machine.current_stitchout_id.with_context(tz=self.tz)
        job = stitchout.job_id
        if job:
            data['job'] = {
                'name': job.name,
                'title': job.title or '',
                'customer': job.partner_id.display_name or '',
                'product': job.product_id.display_name or '',
                'qty': job.product_qty,
                'qty_done': job.qty_done,
                'operator': job.user_id.name or '',
                'deadline': job.date_deadline.strftime('%d/%m/%Y') if job.date_deadline else '',
                'overdue': bool(job.date_deadline and job.date_deadline < fields.Date.context_today(
                    self.with_context(tz=self.tz))),
                'design': stitchout.design_id.name or '',
                'preview_url': image_url(stitchout.design_id) if stitchout.design_id.image_128 else '',
            }
            progress = stitchout._progress_data()
            data['stitchout'] = {
                'name': stitchout.name,
                'piece': stitchout.piece_number,
                'state': stitchout.state,
                'progress': progress['progress'],
                'live': progress['live'],
                'stitch': progress['stitch'],
                'total_stitches': progress['total_stitches'],
                'color_number': progress['color_number'],
                'color_count': progress['color_count'],
                'color_name': progress['color_name'],
                'color_hex': progress['color_hex'],
                'next_color_name': progress['next_color_name'],
                'elapsed': progress['elapsed'],
                'remaining': progress['remaining'],
                'eta': self._format_time(fields.Datetime.add(now, seconds=progress['remaining_seconds']), now),
                'error_message': progress['error_message'],
            }
        if self.show_queue and self.queue_size > 0:
            queued = self.env['embroidery.job'].search([
                ('machine_id', '=', machine.id),
                ('state', 'in', ('ready', 'in_progress')),
                ('id', '!=', job.id),
            ], limit=self.queue_size)
            data['queue'] = [{
                'name': j.name,
                'title': j.title or '',
                'customer': j.partner_id.display_name or '',
                'pieces': j.qty_remaining,
                'time': format_duration(j.estimated_total_seconds) if j.estimated_total_seconds else '',
            } for j in queued]
        return data

    def _display_data(self, image_url, logo_url=''):
        """Everything the status page shows. ``image_url(design)`` gives a
        design preview's URL as the page will fetch it."""
        self.ensure_one()
        now = fields.Datetime.now()
        machines = [self._machine_data(machine, now, image_url) for machine in self._machines()]
        counts = {}
        for machine in machines:
            counts[machine['status']] = counts.get(machine['status'], 0) + 1
        return {
            'board': {
                'id': self.id,
                'title': self.title or self.name,
                'layout': self.layout,
                'columns': max(self.columns, 0),
                'theme': self.theme,
                'font_scale': self.font_scale,
                'refresh_seconds': max(self.refresh_seconds, 2),
                'rotate_seconds': max(self.rotate_seconds, 3),
                'tz': self.tz,
                'logo_url': logo_url if self.show_logo else '',
                'show': {key[5:]: self[key] for key in self._fields if key.startswith('show_')},
            },
            'summary': counts,
            'machines': machines,
            'updated': self._format_time(now, now),
        }

    def action_preview(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/embroidery/board/%s/preview' % self.id,
            'target': 'new',
        }

    def action_view_displays(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('embroidery_jobbing.action_embroidery_display')
        action['domain'] = [('board_id', '=', self.id)]
        action['context'] = {'default_board_id': self.id}
        return action


class EmbroideryDisplay(models.Model):
    """A Raspberry Pi plugged into a TV, showing a status board full screen.

    The Pi runs a small agent that shows the board in Chromium and signs
    every request to Odoo with the key it got when it was paired, so the
    screen needs no login and no secret address.
    """
    _name = 'embroidery.display'
    _description = 'Embroidery Status Display'
    _inherit = ['embroidery.device.mixin']
    _order = 'name'
    _device_kind = 'display'

    name = fields.Char(required=True, help='e.g. "Workshop TV".')
    active = fields.Boolean(default=True)
    board_id = fields.Many2one(
        'embroidery.status.board', string='Status Board', required=True, ondelete='restrict',
        help='What this screen shows. Change it here and the screen switches within a few seconds.',
    )
    location_note = fields.Char(string='Located', help='Where the screen is, e.g. "Above the embroidery bench".')
    last_seen = fields.Datetime(readonly=True, copy=False)
    last_ip = fields.Char(string='Last Address', readonly=True, copy=False)
    agent_version = fields.Char(readonly=True, copy=False)
    screen_size = fields.Char(readonly=True, copy=False, help='Screen size the display reported, in pixels.')
    is_online = fields.Boolean(string='Online', compute='_compute_is_online')
    reload_counter = fields.Integer(readonly=True, copy=False)
    note = fields.Text(string='Notes')

    @api.depends('last_seen')
    def _compute_is_online(self):
        limit = fields.Datetime.now() - DISPLAY_OFFLINE_AFTER
        for display in self:
            display.is_online = bool(display.last_seen and display.last_seen >= limit)

    def _install_command(self, code):
        base = self.get_base_url().rstrip('/')
        return 'curl -fsSL %s/embroidery/display/install.sh | sudo bash -s -- --url %s --pair %s' % (
            shlex.quote(base), shlex.quote(base), shlex.quote(code))

    def _heartbeat(self, ip, screen_size=None, version=None):
        """Note that the screen asked for data (written at most every 30 s)."""
        self.ensure_one()
        now = fields.Datetime.now()
        vals = {}
        if not self.last_seen or now - self.last_seen >= DISPLAY_HEARTBEAT_EVERY:
            vals['last_seen'] = now
        for field, value in (('last_ip', ip), ('screen_size', screen_size), ('agent_version', version)):
            if value and value != self[field]:
                vals[field] = value
        if vals:
            self.write(vals)

    def action_reload_screen(self):
        """Make the screen reload the page (e.g. after an update)."""
        for display in self:
            display.reload_counter += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': 'success', 'message': _('The screen reloads within a few seconds.')},
        }

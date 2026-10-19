# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

DRIVER_SELECTION = [
    ('manual', 'Manual (download the file)'),
    ('folder', 'Bridge: copy to a folder'),
    ('simulator', 'Bridge: simulator (testing)'),
]

# Drivers that deliver through an Embroidery Bridge.
BRIDGE_DRIVERS = ('folder', 'simulator')

MACHINE_STATUS_SELECTION = [
    ('offline', 'Offline'),
    ('idle', 'Idle'),
    ('waiting', 'Waiting to Start'),
    ('stitching', 'Stitching'),
    ('paused', 'Paused'),
    ('error', 'Error'),
]

DEFAULT_SPEED_SPM = 800
DEFAULT_COLOR_CHANGE_SECONDS = 15


class EmbroideryMachine(models.Model):
    _name = 'embroidery.machine'
    _description = 'Embroidery Machine'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(required=True, tracking=True, help='e.g. "PR1060W #1".')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, tracking=True,
    )
    color = fields.Integer(string='Colour Index')

    # ── Machine ───────────────────────────────────────────────────────────
    machine_model_id = fields.Many2one('embroidery.machine.model', string='Model', tracking=True)
    needle_count = fields.Integer(
        string='Needles', compute='_compute_from_model', store=True, readonly=False,
    )
    speed_spm = fields.Integer(
        string='Running Speed (spm)', compute='_compute_from_model', store=True, readonly=False,
        help='The speed you usually stitch at, in stitches per minute. Used for time estimates.',
    )
    color_change_seconds = fields.Integer(
        string='Colour Change Time (s)', default=DEFAULT_COLOR_CHANGE_SECONDS,
        help='Average time a colour change adds, including any thread trimming. Used for time estimates.',
    )
    hoop_ids = fields.Many2many(
        'embroidery.hoop', string='Hoops & Frames',
        compute='_compute_from_model', store=True, readonly=False,
    )
    serial_number = fields.Char(tracking=True)
    ip_address = fields.Char(string='IP Address', help="The machine's address on the workshop network.")
    location_note = fields.Char(string='Located', help='Where the machine is, e.g. "Workshop bench 2".')
    note = fields.Html(string='Notes')

    # ── Connection ────────────────────────────────────────────────────────
    driver = fields.Selection(
        DRIVER_SELECTION, required=True, default='manual', tracking=True,
        help='How designs reach the machine:\n'
             '- Manual: the operator downloads the .pes file (USB stick, Brother software) '
             'and reports progress from Odoo.\n'
             '- Copy to a folder: the Embroidery Bridge saves the file into a folder on its PC, '
             'e.g. a USB stick or the folder your Brother software sends from.\n'
             '- Simulator: the Embroidery Bridge pretends to stitch the design, '
             'to try the whole flow without a machine.',
    )
    bridge_id = fields.Many2one('embroidery.bridge', string='Bridge', tracking=True)
    drop_folder = fields.Char(
        string='Folder on Bridge PC',
        help='Folder the bridge saves designs into, e.g. E:\\ or C:\\Embroidery\\To Machine.',
    )
    bridge_reported_online = fields.Boolean(readonly=True, copy=False)
    bridge_message = fields.Char(string='Bridge Message', readonly=True, copy=False)

    # ── Status ────────────────────────────────────────────────────────────
    stitchout_ids = fields.One2many('embroidery.stitchout', 'machine_id', string='Stitch Outs')
    current_stitchout_id = fields.Many2one(
        'embroidery.stitchout', string='Current Stitch Out', compute='_compute_current_stitchout',
    )
    current_job_id = fields.Many2one(
        'embroidery.job', string='Current Job', compute='_compute_current_stitchout',
    )
    current_progress = fields.Float(string='Progress', compute='_compute_current_stitchout')
    status = fields.Selection(MACHINE_STATUS_SELECTION, compute='_compute_status')
    last_seen = fields.Datetime(related='bridge_id.last_seen', string='Bridge Last Seen')
    stitchout_count = fields.Integer(compute='_compute_stats', string='Stitch Outs Done')
    stitches_done = fields.Integer(compute='_compute_stats', string='Stitches Done')

    @api.depends('machine_model_id')
    def _compute_from_model(self):
        for machine in self:
            model = machine.machine_model_id
            if model:
                machine.needle_count = model.needle_count
                machine.speed_spm = min(model.max_speed_spm or DEFAULT_SPEED_SPM, DEFAULT_SPEED_SPM)
                machine.hoop_ids = model.hoop_ids
            elif not machine.speed_spm:
                machine.speed_spm = DEFAULT_SPEED_SPM

    def _open_stitchouts(self):
        return self.env['embroidery.stitchout'].search(
            [('machine_id', 'in', self.ids), ('state', 'in', self.env['embroidery.stitchout']._OPEN_STATES)],
            order='id',
        )

    @api.depends('stitchout_ids.state', 'stitchout_ids.current_stitch')
    def _compute_current_stitchout(self):
        open_by_machine = {}
        for stitchout in self._open_stitchouts():
            open_by_machine.setdefault(stitchout.machine_id.id, stitchout)
        for machine in self:
            stitchout = open_by_machine.get(machine.id, self.env['embroidery.stitchout'])
            machine.current_stitchout_id = stitchout
            machine.current_job_id = stitchout.job_id
            machine.current_progress = stitchout.progress if stitchout else 0.0

    @api.depends('driver', 'bridge_id.last_seen', 'bridge_reported_online', 'current_stitchout_id')
    def _compute_status(self):
        for machine in self:
            stitchout = machine.current_stitchout_id
            if machine.driver in BRIDGE_DRIVERS and not (
                machine.bridge_id.is_online and machine.bridge_reported_online
            ):
                machine.status = 'offline'
            elif not stitchout:
                machine.status = 'idle'
            elif stitchout.state in ('queued', 'sent'):
                machine.status = 'waiting'
            else:
                machine.status = stitchout.state

    def _compute_stats(self):
        groups = self.env['embroidery.stitchout']._read_group(
            [('machine_id', 'in', self.ids), ('state', '=', 'done')],
            ['machine_id'], ['__count', 'total_stitches:sum'],
        )
        stats = {machine.id: (count, stitches) for machine, count, stitches in groups}
        for machine in self:
            machine.stitchout_count, machine.stitches_done = stats.get(machine.id, (0, 0))

    def _estimate_seconds(self, stitches, color_changes):
        """Seconds to stitch ``stitches`` with ``color_changes`` on this machine."""
        speed = (self.speed_spm if self else 0) or DEFAULT_SPEED_SPM
        change = self.color_change_seconds if self else DEFAULT_COLOR_CHANGE_SECONDS
        return stitches / speed * 60.0 + max(color_changes, 0) * change

    def _bridge_config(self):
        """What the bridge needs to know about the machine."""
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'driver': self.driver,
            'drop_folder': self.drop_folder or '',
            'ip_address': self.ip_address or '',
            'speed_spm': self.speed_spm or DEFAULT_SPEED_SPM,
            'color_change_seconds': self.color_change_seconds,
        }

    def action_view_stitchouts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('embroidery_jobbing.action_embroidery_stitchout')
        action['domain'] = [('machine_id', '=', self.id)]
        action['context'] = {'default_machine_id': self.id}
        action['name'] = _('Stitch Outs: %s', self.name)
        return action

    def action_open_current_job(self):
        self.ensure_one()
        if not self.current_job_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'embroidery.job',
            'res_id': self.current_job_id.id,
            'view_mode': 'form',
        }

    def embroidery_progress_data(self):
        """Data for the progress monitor: the machine's current stitch out."""
        self.ensure_one()
        return self.current_stitchout_id._progress_data(machine=self)

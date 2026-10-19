# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .embroidery_stitchout import format_duration

JOB_STATE_SELECTION = [
    ('draft', 'Draft'),
    ('ready', 'Ready'),
    ('in_progress', 'In Progress'),
    ('done', 'Done'),
    ('cancelled', 'Cancelled'),
]


class EmbroideryJob(models.Model):
    """An embroidery work order: what to embroider, on what, and how many."""
    _name = 'embroidery.job'
    _description = 'Embroidery Job'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, date_deadline, id desc'
    # The machine is chosen for the job, it isn't where the job belongs.
    _org_parent_field = False

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    title = fields.Char(string='Job Title', tracking=True, help='Short description, e.g. "Club polos - left chest logo".')
    state = fields.Selection(JOB_STATE_SELECTION, string='Status', default='draft', required=True,
                             tracking=True, copy=False)
    priority = fields.Selection([('0', 'Normal'), ('1', 'Urgent')], default='0', tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, tracking=True)
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True)
    user_id = fields.Many2one('res.users', string='Assigned To', default=lambda self: self.env.user,
                              tracking=True, domain="[('share', '=', False)]")
    date_deadline = fields.Date(string='Due Date', tracking=True)
    date_done = fields.Datetime(string='Completed On', readonly=True, copy=False)

    # ── What is needed ────────────────────────────────────────────────────
    product_id = fields.Many2one('product.product', string='Product', tracking=True,
                                 help='The garment or item being embroidered.')
    product_qty = fields.Integer(string='Pieces', default=1, required=True, tracking=True,
                                 help='How many pieces to embroider.')
    item_colour = fields.Char(string='Item Colour', help='Colour of the garment or fabric.')
    item_size = fields.Char(string='Sizes', help='e.g. "4 x M, 6 x L".')
    placement_id = fields.Many2one('embroidery.placement', string='Placement', tracking=True)
    stabiliser_id = fields.Many2one('embroidery.stabiliser', string='Stabiliser', tracking=True)
    hoop_id = fields.Many2one('embroidery.hoop', string='Hoop / Frame', tracking=True)
    instructions = fields.Html(string='Instructions')

    # ── Design ────────────────────────────────────────────────────────────
    design_id = fields.Many2one('embroidery.design', string='Design', tracking=True,
                                domain="[('company_id', '=', company_id)]")
    design_file = fields.Binary(related='design_id.design_file', string='Design File')
    design_filename = fields.Char(related='design_id.design_filename')
    design_image = fields.Image(related='design_id.image_512', string='Preview')
    stitch_count = fields.Integer(related='design_id.stitch_count')
    color_count = fields.Integer(related='design_id.color_count')
    design_size = fields.Char(related='design_id.size_display', string='Design Size')
    design_color_ids = fields.One2many(related='design_id.color_ids', string='Thread Colours')

    # ── Machine ───────────────────────────────────────────────────────────
    machine_id = fields.Many2one('embroidery.machine', string='Machine', tracking=True,
                                 domain="[('company_id', '=', company_id)]")
    machine_status = fields.Selection(related='machine_id.status', string='Machine Status')
    allowed_hoop_ids = fields.Many2many('embroidery.hoop', compute='_compute_allowed_hoop_ids')
    estimated_seconds = fields.Integer(string='Time per Piece', compute='_compute_estimates',
                                       help='Estimated stitching time for one piece on the chosen machine.')
    estimated_total_seconds = fields.Integer(string='Seconds Remaining (est.)', compute='_compute_estimates',
                                             help='Estimated stitching time for the pieces still to do.')
    estimated_display = fields.Char(string='Time per Piece (est.)', compute='_compute_estimates')
    estimated_total_display = fields.Char(string='Time Remaining (est.)', compute='_compute_estimates')
    warning_message = fields.Text(compute='_compute_warning_message')

    # ── Stitch outs ───────────────────────────────────────────────────────
    stitchout_ids = fields.One2many('embroidery.stitchout', 'job_id', string='Stitch Outs')
    stitchout_count = fields.Integer(compute='_compute_stitchout_count')
    qty_done = fields.Integer(string='Pieces Done', compute='_compute_qty_done', store=True)
    qty_remaining = fields.Integer(string='Pieces To Do', compute='_compute_qty_done', store=True)
    current_stitchout_id = fields.Many2one('embroidery.stitchout', compute='_compute_current_stitchout',
                                           string='Current Stitch Out')
    has_open_stitchout = fields.Boolean(compute='_compute_current_stitchout')
    progress = fields.Float(compute='_compute_current_stitchout', string='Progress',
                            help='Progress of the current stitch out.')
    error_count = fields.Integer(compute='_compute_stitchout_count', string='Errors')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('embroidery.job') or _('New')
        return super().create(vals_list)

    @api.depends('machine_id', 'machine_id.hoop_ids')
    def _compute_allowed_hoop_ids(self):
        all_hoops = self.env['embroidery.hoop'].search([])
        for job in self:
            job.allowed_hoop_ids = job.machine_id.hoop_ids or all_hoops

    @api.depends('stitchout_ids.state', 'product_qty')
    def _compute_qty_done(self):
        for job in self:
            job.qty_done = len(job.stitchout_ids.filtered(lambda s: s.state == 'done'))
            job.qty_remaining = max(job.product_qty - job.qty_done, 0)

    @api.depends('stitchout_ids.error_count')
    def _compute_stitchout_count(self):
        for job in self:
            job.stitchout_count = len(job.stitchout_ids)
            job.error_count = sum(job.stitchout_ids.mapped('error_count'))

    @api.depends('stitchout_ids.state', 'stitchout_ids.current_stitch')
    def _compute_current_stitchout(self):
        for job in self:
            stitchouts = job.stitchout_ids.sorted('id')
            current = stitchouts.filtered(lambda s: s.state in s._OPEN_STATES)[:1] or stitchouts[-1:]
            job.current_stitchout_id = current
            job.has_open_stitchout = current.state in current._OPEN_STATES if current else False
            job.progress = current.progress if current else 0.0

    @api.depends('design_id.stitch_count', 'design_id.color_change_count', 'machine_id.speed_spm',
                 'machine_id.color_change_seconds', 'qty_remaining')
    def _compute_estimates(self):
        for job in self:
            if not job.design_id:
                job.estimated_seconds = job.estimated_total_seconds = 0
                job.estimated_display = job.estimated_total_display = False
                continue
            seconds = job.machine_id._estimate_seconds(job.design_id.stitch_count, job.design_id.color_change_count)
            job.estimated_seconds = round(seconds)
            job.estimated_total_seconds = round(seconds * job.qty_remaining)
            job.estimated_display = format_duration(job.estimated_seconds)
            job.estimated_total_display = format_duration(job.estimated_total_seconds)

    @api.depends('design_id', 'machine_id', 'hoop_id')
    def _compute_warning_message(self):
        for job in self:
            job.warning_message = '\n'.join(job._warnings()) or False

    def _warnings(self):
        self.ensure_one()
        warnings = []
        design, machine, hoop = self.design_id, self.machine_id, self.hoop_id
        if not design.stitch_count:
            return warnings
        width, height = design.width_mm, design.height_mm
        if hoop and not hoop._fits(width, height):
            warnings.append(_('The design (%(size)s) is bigger than the %(hoop)s.',
                              size=design.size_display, hoop=hoop.display_name))
        model = machine.machine_model_id
        if model.max_width_mm and model.max_height_mm and not (
            (width <= model.max_width_mm and height <= model.max_height_mm)
            or (width <= model.max_height_mm and height <= model.max_width_mm)
        ):
            warnings.append(_('The design (%(size)s) is bigger than %(machine)s can stitch (%(w)g x %(h)g mm).',
                              size=design.size_display, machine=machine.name,
                              w=model.max_width_mm, h=model.max_height_mm))
        if machine.needle_count and design.color_count > machine.needle_count:
            warnings.append(_('The design uses %(colours)s colours but %(machine)s has %(needles)s needles: '
                              'some needles will need re-threading during the stitch out.',
                              colours=design.color_count, machine=machine.name, needles=machine.needle_count))
        return warnings

    @api.onchange('machine_id')
    def _onchange_machine_id(self):
        if self.hoop_id and self.machine_id.hoop_ids and self.hoop_id not in self.machine_id.hoop_ids:
            self.hoop_id = False

    # ── Actions ───────────────────────────────────────────────────────────
    def action_confirm(self):
        for job in self:
            if not job.design_id:
                raise UserError(_('Choose the design for %s before marking it ready.', job.name))
        self.filtered(lambda j: j.state == 'draft').state = 'ready'

    def action_send_to_machine(self):
        """Send the design to the job's machine to stitch the next piece."""
        self.ensure_one()
        if self.state in ('done', 'cancelled'):
            raise UserError(_('%s is %s.', self.name, dict(JOB_STATE_SELECTION)[self.state].lower()))
        if not self.design_id:
            raise UserError(_('Choose the design to send.'))
        if not self.machine_id:
            raise UserError(_('Choose the machine to send the design to.'))
        if not self.qty_remaining:
            raise UserError(_('All %s pieces of %s are done.', self.product_qty, self.name))
        machine = self.machine_id
        busy = machine.current_stitchout_id
        if busy:
            raise UserError(_('%(machine)s is busy with %(stitchout)s (%(state)s). Finish or cancel it first.',
                              machine=machine.name, stitchout=busy.display_name,
                              state=dict(busy._fields['state'].selection)[busy.state]))
        if machine.driver != 'manual' and not machine.bridge_id:
            raise UserError(_('%s has no Embroidery Bridge set up to deliver the file. Set its bridge, '
                              'or switch its connection to Manual.', machine.name))
        stitchout = self.env['embroidery.stitchout'].create({
            'job_id': self.id,
            'machine_id': machine.id,
            'design_id': self.design_id.id,
        })
        if self.state in ('draft', 'ready'):
            self.state = 'in_progress'
        self.message_post(body=_('Piece %(piece)s sent to %(machine)s (%(design)s).',
                                 piece=stitchout.piece_number, machine=machine.name, design=self.design_id.name))
        return True

    def action_mark_done(self):
        self.write({'state': 'done', 'date_done': fields.Datetime.now()})

    def action_cancel(self):
        for job in self:
            job.stitchout_ids.filtered(lambda s: s.state in s._OPEN_STATES)._set_state('cancelled')
        self.state = 'cancelled'

    def action_reset_draft(self):
        self.write({'state': 'draft', 'date_done': False})

    def action_view_stitchouts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('embroidery_jobbing.action_embroidery_stitchout')
        action['domain'] = [('job_id', '=', self.id)]
        action['context'] = {'default_job_id': self.id, 'create': False}
        return action

    def action_download_design(self):
        self.ensure_one()
        if not self.design_id:
            raise UserError(_('Choose the design first.'))
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/embroidery.design/%s/design_file/%s?download=true'
                   % (self.design_id.id, self.design_id.design_filename or 'design.pes'),
            'target': 'self',
        }

    def _check_complete(self):
        """Finish the job once every piece has been stitched."""
        for job in self.filtered(lambda j: j.state == 'in_progress' and j.qty_done >= j.product_qty):
            job.write({'state': 'done', 'date_done': fields.Datetime.now()})
            job.message_post(body=_('All %s pieces are done.', job.product_qty))

    def embroidery_progress_data(self):
        """Data for the progress monitor: the job's current stitch out."""
        self.ensure_one()
        return self.current_stitchout_id._progress_data(job=self)

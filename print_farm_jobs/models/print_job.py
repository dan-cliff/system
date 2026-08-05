import logging

from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


JOB_STATE_SELECTION = [
    ('draft', 'Draft'),
    ('queued', 'Queued'),
    ('sending', 'Sending to Printer'),
    ('printing', 'Printing'),
    ('paused', 'Paused'),
    ('done', 'Done'),
    ('failed', 'Failed'),
    ('cancelled', 'Cancelled'),
]

PRIORITY_SELECTION = [
    ('0', 'Normal'),
    ('1', 'Urgent'),
]


class PrintJobFilament(models.Model):
    _name = 'print.job.filament'
    _description = 'Required Filament for Print Job'
    _order = 'sequence, id'

    job_id = fields.Many2one(
        'print.job',
        string='Job',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    filament_id = fields.Many2one(
        'print.filament',
        string='Required Filament',
        required=True,
    )
    estimated_weight_g = fields.Float(
        string='Estimated Usage (g)',
        help='Approximate filament weight needed for this colour/material',
    )
    # Read-only display helpers
    material = fields.Selection(related='filament_id.material', string='Material', readonly=True)
    color_hex = fields.Char(related='filament_id.color_hex', string='Colour', readonly=True)


class PrintJob(models.Model):
    _name = 'print.job'
    _description = 'Print Farm Job'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, queue_position, id'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Job Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )
    job_title = fields.Char(string='Job Title')
    job_description = fields.Text(string='Job Description')
    priority = fields.Selection(
        PRIORITY_SELECTION,
        string='Priority',
        default='0',
        tracking=True,
    )
    queue_position = fields.Integer(
        string='Queue Position',
        default=0,
        tracking=True,
        help='Lower number = higher priority in queue',
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        JOB_STATE_SELECTION,
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    date_queued = fields.Datetime(string='Queued On', readonly=True, copy=False)
    date_sent = fields.Datetime(string='Sent to Printer', readonly=True, copy=False)
    date_started = fields.Datetime(string='Print Started', readonly=True, copy=False)
    date_done = fields.Datetime(string='Completed', readonly=True, copy=False)
    error_message = fields.Text(string='Error / Failure Reason', readonly=True, copy=False)

    # ── File ──────────────────────────────────────────────────────────────────
    job_file = fields.Binary(
        string='Print File (.3mf / .gcode)',
        attachment=True,
        help='Upload the sliced .3mf or .gcode file to be sent to the printer',
    )
    job_filename = fields.Char(string='File Name')
    file_size_kb = fields.Float(
        string='File Size (KB)',
        compute='_compute_file_size',
    )

    # ── Filament Requirements ─────────────────────────────────────────────────
    required_filament_ids = fields.One2many(
        'print.job.filament',
        'job_id',
        string='Required Filaments',
    )
    filament_count = fields.Integer(
        compute='_compute_filament_count',
        string='# Filaments',
    )

    # ── Printer Assignment ─────────────────────────────────────────────────────
    printer_id = fields.Many2one(
        'print.printer',
        string='Assigned Printer',
        tracking=True,
        domain=[('active', '=', True)],
    )
    auto_assign = fields.Boolean(
        string='Auto-assign Printer',
        default=True,
        help='Automatically select the best available printer based on loaded filaments',
    )
    compatible_printer_ids = fields.Many2many(
        'print.printer',
        compute='_compute_compatible_printers',
        string='Compatible Printers',
        help='Printers that have all required filaments currently loaded',
    )
    compatible_printer_count = fields.Integer(
        compute='_compute_compatible_printers',
        string='# Compatible Printers',
    )

    # ── Print Settings ────────────────────────────────────────────────────────
    plate_number = fields.Integer(
        string='Plate Number',
        default=1,
        help='Plate to print from the .3mf file (default: 1)',
    )
    use_ams = fields.Boolean(
        string='Use AMS',
        default=True,
        help='Whether to use the AMS for multi-colour printing',
    )
    bed_leveling = fields.Boolean(string='Bed Levelling', default=True)
    flow_calibration = fields.Boolean(string='Flow Calibration', default=False)
    vibration_calibration = fields.Boolean(string='Vibration Calibration', default=True)
    layer_inspect = fields.Boolean(string='AI Layer Inspect', default=False)
    timelapse = fields.Boolean(string='Timelapse', default=False)

    # ── Source Sale Order ─────────────────────────────────────────────────────
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Source Sale Order',
        ondelete='set null',
        index=True,
        copy=False,
        readonly=True,
    )

    # ── Estimated Stats ───────────────────────────────────────────────────────
    estimated_time_minutes = fields.Integer(
        string='Est. Print Time (min)',
        help='Estimated total print time in minutes',
    )
    total_filament_g = fields.Float(
        string='Total Filament (g)',
        compute='_compute_total_filament',
        store=True,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Computed
    # ─────────────────────────────────────────────────────────────────────────

    @api.depends('job_file')
    def _compute_file_size(self):
        for rec in self:
            if rec.job_file:
                import base64
                try:
                    rec.file_size_kb = len(base64.b64decode(rec.job_file)) / 1024.0
                except Exception:
                    rec.file_size_kb = 0.0
            else:
                rec.file_size_kb = 0.0

    @api.depends('required_filament_ids')
    def _compute_filament_count(self):
        for rec in self:
            rec.filament_count = len(rec.required_filament_ids)

    @api.depends('required_filament_ids.estimated_weight_g')
    def _compute_total_filament(self):
        for rec in self:
            rec.total_filament_g = sum(rec.required_filament_ids.mapped('estimated_weight_g'))

    @api.depends('required_filament_ids.filament_id', 'state')
    def _compute_compatible_printers(self):
        all_printers = self.env['print.printer'].search([('active', '=', True)])
        for rec in self:
            if not rec.required_filament_ids:
                rec.compatible_printer_ids = all_printers
            else:
                compatible = all_printers.filtered(lambda p: p.can_print_job(rec))
                rec.compatible_printer_ids = compatible
            rec.compatible_printer_count = len(rec.compatible_printer_ids)

    # ─────────────────────────────────────────────────────────────────────────
    # Sequence
    # ─────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('print.job') or _('New')
        return super().create(vals_list)

    # ─────────────────────────────────────────────────────────────────────────
    # Auto-assign printer logic
    # ─────────────────────────────────────────────────────────────────────────

    def _find_best_printer(self):
        """Return the best available printer for this job, or False."""
        self.ensure_one()
        candidates = self.compatible_printer_ids

        if not candidates:
            return False

        # Prefer idle printers
        idle = candidates.filtered(lambda p: p.state == 'idle')
        pool = idle if idle else candidates

        # Among the pool, prefer the one with fewest queued jobs (load balancing)
        return min(pool, key=lambda p: p.queued_job_count, default=False)

    # ─────────────────────────────────────────────────────────────────────────
    # State transitions
    # ─────────────────────────────────────────────────────────────────────────

    def action_queue(self):
        """Move the job to the queue."""
        for job in self:
            if job.state != 'draft':
                raise UserError(_('Only draft jobs can be queued.'))
            if not job.job_file:
                raise UserError(_('Job "%s" has no print file attached.') % job.name)

            # Auto-assign printer if requested
            if job.auto_assign and not job.printer_id:
                best = job._find_best_printer()
                if best:
                    job.printer_id = best

            job.write({
                'state': 'queued',
                'date_queued': fields.Datetime.now(),
            })
            job.message_post(body=_('Job queued.'))

    def action_send_to_printer(self):
        """Send the job to the assigned printer via API."""
        self.ensure_one()
        job = self

        if job.state not in ('queued', 'draft'):
            raise UserError(
                _('Job "%s" cannot be sent in its current state (%s).') % (job.name, job.state)
            )
        if not job.printer_id:
            raise UserError(
                _('Job "%s" has no printer assigned. '
                  'Please assign a printer or enable auto-assign.') % job.name
            )
        if not job.job_file:
            raise UserError(_('Job "%s" has no print file attached.') % job.name)

        printer = job.printer_id

        job.write({'state': 'sending'})
        try:
            if printer.agent_url:
                # Odoo.sh / remote: delegate all printer communication to the
                # local Print Farm Agent running on the same LAN as the printer
                printer._agent_send_job(job)
            else:
                # Local: Odoo is on the same network as the printer
                remote_path = printer._ftps_upload_file(
                    job.job_file, job.job_filename or (job.name + '.3mf')
                )
                printer._mqtt_send_print_command(remote_path, job)

            job.write({
                'state': 'printing',
                'date_sent': fields.Datetime.now(),
                'date_started': fields.Datetime.now(),
                'error_message': False,
            })
            printer.write({
                'state': 'printing',
                'current_job_id': job.id,
            })
            job.message_post(
                body=Markup(_('Job sent to printer <b>%s</b> successfully.')) % printer.name
            )
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Job Sent'),
                    'message': _('"%s" has been sent to %s.') % (job.name, printer.name),
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                },
            }
        except Exception as e:
            error_msg = str(e)
            job.write({
                'state': 'failed',
                'error_message': error_msg,
            })
            job.message_post(body=_('Failed to send job: %s') % error_msg)
            # Flush writes before returning so they are committed even though
            # we are not raising (raising would roll back the whole transaction).
            job.env.cr.flush()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Failed to Send Job'),
                    'message': error_msg,
                    'type': 'danger',
                    'sticky': True,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                },
            }

    def action_mark_done(self):
        for job in self:
            job.write({
                'state': 'done',
                'date_done': fields.Datetime.now(),
            })
            if job.printer_id and job.printer_id.current_job_id == job:
                job.printer_id.write({'state': 'idle', 'current_job_id': False})
            job.message_post(body=_('Job marked as complete.'))

    def action_mark_failed(self):
        for job in self:
            job.write({'state': 'failed', 'date_done': fields.Datetime.now()})
            if job.printer_id and job.printer_id.current_job_id == job:
                job.printer_id.write({'state': 'idle', 'current_job_id': False})

    def action_cancel(self):
        for job in self:
            if job.state in ('done',):
                raise UserError(_('Completed jobs cannot be cancelled.'))
            job.write({'state': 'cancelled'})
            if job.printer_id and job.printer_id.current_job_id == job:
                job.printer_id.write({'state': 'idle', 'current_job_id': False})
            job.message_post(body=_('Job cancelled.'))

    def action_reprint(self):
        """Duplicate this job as a fresh draft and open the new record."""
        self.ensure_one()
        new_job = self.copy({
            'state': 'draft',
            'job_title': self.job_title,
            'job_description': self.job_description,
            'date_queued': False,
            'date_sent': False,
            'date_started': False,
            'date_done': False,
            'error_message': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'print.job',
            'res_id': new_job.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_reset_draft(self):
        for job in self:
            if job.state not in ('cancelled', 'failed'):
                raise UserError(_('Only cancelled or failed jobs can be reset to draft.'))
            job.write({'state': 'draft', 'error_message': False})

    def action_open_assign_wizard(self):
        """Open the printer assignment wizard."""
        self.ensure_one()
        return {
            'name': _('Assign Printer'),
            'type': 'ir.actions.act_window',
            'res_model': 'print.job.assign.printer.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_job_id': self.id},
        }


class SaleOrderPrintFarm(models.Model):
    """Extend sale.order with print farm link."""
    _inherit = 'sale.order'

    print_job_ids = fields.One2many(
        'print.job',
        'sale_order_id',
        string='Print Jobs',
    )
    print_job_count = fields.Integer(
        compute='_compute_print_job_count',
        string='Print Job Count',
    )

    @api.depends('print_job_ids')
    def _compute_print_job_count(self):
        for rec in self:
            rec.print_job_count = len(rec.print_job_ids)

    def action_view_print_jobs(self):
        self.ensure_one()
        return {
            'name': _('Print Jobs'),
            'type': 'ir.actions.act_window',
            'res_model': 'print.job',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
        }

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PrintJobAssignPrinterWizard(models.TransientModel):
    _name = 'print.job.assign.printer.wizard'
    _description = 'Assign Printer to Print Job'

    job_id = fields.Many2one(
        'print.job',
        string='Print Job',
        required=True,
        readonly=True,
    )
    job_title = fields.Char(related='job_id.job_title', string='Job Title', readonly=True)
    printer_id = fields.Many2one(
        'print.printer',
        string='Printer',
        required=True,
        domain=[('active', '=', True)],
    )
    compatible_only = fields.Boolean(
        string='Compatible Printers Only',
        default=True,
        help='Show only printers that have all required filaments loaded',
    )
    compatible_printer_ids = fields.Many2many(
        'print.printer',
        compute='_compute_compatible_printers',
        string='Compatible Printers',
    )
    send_immediately = fields.Boolean(
        string='Send to Printer Immediately',
        default=True,
        help='If checked, the job will be sent to the printer right after assignment',
    )

    @api.depends('job_id')
    def _compute_compatible_printers(self):
        for wiz in self:
            wiz.compatible_printer_ids = wiz.job_id.compatible_printer_ids

    def action_assign(self):
        """Assign the selected printer and optionally send the job."""
        self.ensure_one()
        job = self.job_id
        if not self.printer_id:
            raise UserError(_('Please select a printer.'))
        job.printer_id = self.printer_id
        if self.send_immediately:
            if job.state == 'draft':
                job.action_queue()
            job.action_send_to_printer()
        return {'type': 'ir.actions.act_window_close'}

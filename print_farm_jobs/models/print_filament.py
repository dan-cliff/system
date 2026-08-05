import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


MATERIAL_SELECTION = [
    ('pla', 'PLA'),
    ('pla_cf', 'PLA-CF'),
    ('petg', 'PETG'),
    ('petg_cf', 'PETG-CF'),
    ('abs', 'ABS'),
    ('asa', 'ASA'),
    ('tpu', 'TPU'),
    ('pa', 'PA (Nylon)'),
    ('pa_cf', 'PA-CF'),
    ('pc', 'PC'),
    ('pva', 'PVA'),
    ('hips', 'HIPS'),
    ('other', 'Other'),
]

SPOOL_STATE_SELECTION = [
    ('new', 'New / Unused'),
    ('in_use', 'In Use'),
    ('empty', 'Empty'),
    ('discarded', 'Discarded'),
]


class PrintFilament(models.Model):
    _name = 'print.filament'
    _description = 'Filament Type'
    _order = 'material, name'

    name = fields.Char(string='Filament Name', required=True)
    material = fields.Selection(
        MATERIAL_SELECTION,
        string='Material',
        required=True,
        default='pla',
    )
    brand = fields.Char(string='Brand')
    color_name = fields.Char(string='Colour Name')
    color_hex = fields.Char(
        string='Colour (Hex)',
        help='Hex colour code, e.g. #FF5733',
    )
    description = fields.Text(string='Notes')
    active = fields.Boolean(default=True)

    # Computed display name for easy reference
    display_name_full = fields.Char(
        compute='_compute_display_name_full',
        string='Full Name',
        store=True,
    )

    @api.depends('name', 'material', 'brand', 'color_name')
    def _compute_display_name_full(self):
        material_dict = dict(MATERIAL_SELECTION)
        for rec in self:
            parts = []
            if rec.brand:
                parts.append(rec.brand)
            mat = material_dict.get(rec.material, rec.material)
            parts.append(mat)
            if rec.color_name:
                parts.append(rec.color_name)
            rec.display_name_full = ' – '.join(parts) if parts else rec.name

    def name_get(self):
        result = []
        material_dict = dict(MATERIAL_SELECTION)
        for rec in self:
            mat = material_dict.get(rec.material, rec.material)
            label = rec.name
            if rec.color_name:
                label = '%s (%s)' % (rec.name, rec.color_name)
            result.append((rec.id, '[%s] %s' % (mat, label)))
        return result


class PrintFilamentSpool(models.Model):
    _name = 'print.filament.spool'
    _description = 'Filament Spool'
    _order = 'filament_id, id'

    name = fields.Char(
        string='Spool Reference',
        required=True,
        copy=False,
        default=lambda self: _('New'),
    )
    filament_id = fields.Many2one(
        'print.filament',
        string='Filament Type',
        required=True,
        ondelete='restrict',
    )
    state = fields.Selection(
        SPOOL_STATE_SELECTION,
        string='Status',
        default='new',
        required=True,
    )
    weight_total_g = fields.Float(
        string='Total Weight (g)',
        default=1000.0,
        help='Total weight of filament on a new spool',
    )
    weight_remaining_g = fields.Float(
        string='Remaining Weight (g)',
        help='Estimated remaining filament weight',
    )
    purchase_date = fields.Date(string='Purchase Date')
    notes = fields.Text(string='Notes')
    active = fields.Boolean(default=True)

    # Related convenience fields
    material = fields.Selection(
        related='filament_id.material',
        string='Material',
        store=True,
    )
    color_hex = fields.Char(
        related='filament_id.color_hex',
        string='Colour',
        store=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('print.filament.spool') or _('New')
            if 'weight_remaining_g' not in vals or not vals['weight_remaining_g']:
                vals['weight_remaining_g'] = vals.get('weight_total_g', 1000.0)
        return super().create(vals_list)

    def action_mark_in_use(self):
        self.write({'state': 'in_use'})

    def action_mark_empty(self):
        self.write({'state': 'empty'})


class PrintRestockOrder(models.Model):
    _name = 'print.restock.order'
    _description = 'Filament Restock Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Restock Reference',
        required=True,
        copy=False,
        default=lambda self: _('New'),
        readonly=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('received', 'Received'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )
    date = fields.Date(
        string='Order Date',
        default=fields.Date.today,
    )
    line_ids = fields.One2many(
        'print.restock.order.line',
        'order_id',
        string='Lines',
    )
    notes = fields.Text(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('print.restock.order') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if rec.state == 'draft':
                rec.state = 'confirmed'

    def action_receive(self):
        for rec in self:
            if rec.state == 'confirmed':
                rec.state = 'received'

    def action_cancel(self):
        for rec in self:
            if rec.state in ('draft', 'confirmed'):
                rec.state = 'cancelled'

    def action_reset_draft(self):
        for rec in self:
            if rec.state == 'cancelled':
                rec.state = 'draft'


class ResConfigSettingsPrintFarm(models.TransientModel):
    """Extend res.config.settings with Print Farm options."""
    _inherit = 'res.config.settings'

    print_farm_sale_integration = fields.Boolean(
        string='Sales Order Integration',
        config_parameter='print_farm_jobs.sale_integration',
        help='Show Print Jobs smart button on sale orders',
    )
    print_farm_auto_assign = fields.Boolean(
        string='Auto-assign Printers',
        config_parameter='print_farm_jobs.auto_assign',
        help='Automatically assign the best available printer when queueing jobs',
    )


class ProductTemplatePrintFarm(models.Model):
    """Extend product.template with print farm fields."""
    _inherit = 'product.template'

    # ── Enable / Identity ─────────────────────────────────────────────────────
    print_job_enabled = fields.Boolean(
        string='Enable Print Farm',
        default=False,
        help='Enable Print Farm job creation for this product',
    )
    print_job_description = fields.Text(
        string='Print Job Description',
        help='Default description used when creating print jobs for this product',
    )

    # ── Default File ──────────────────────────────────────────────────────────
    print_job_file = fields.Binary(
        string='Default Print File',
        attachment=True,
        help='Default .3mf or .gcode file used when creating print jobs for this product',
    )
    print_job_filename = fields.Char(string='Print File Name')

    # ── Default Print Settings ────────────────────────────────────────────────
    print_job_plate_number = fields.Integer(
        string='Default Plate',
        default=1,
        help='Default plate number to print from the .3mf file',
    )
    print_job_estimated_time_minutes = fields.Integer(
        string='Est. Print Time (min)',
        help='Estimated print time in minutes',
    )
    print_job_use_ams = fields.Boolean(
        string='Use AMS',
        default=True,
    )
    print_job_bed_leveling = fields.Boolean(
        string='Bed Levelling',
        default=True,
    )
    print_job_flow_calibration = fields.Boolean(
        string='Flow Calibration',
        default=False,
    )
    print_job_vibration_calibration = fields.Boolean(
        string='Vibration Calibration',
        default=True,
    )
    print_job_layer_inspect = fields.Boolean(
        string='AI Layer Inspect',
        default=False,
    )
    print_job_timelapse = fields.Boolean(
        string='Timelapse',
        default=False,
    )
    print_job_auto_assign = fields.Boolean(
        string='Auto-assign Printer',
        default=True,
    )

    # ── Filament / Notes ──────────────────────────────────────────────────────
    print_farm_filament_id = fields.Many2one(
        'print.filament',
        string='Default Filament',
        help='Default filament type used when creating print jobs for this product',
    )
    print_farm_notes = fields.Text(
        string='Print Farm Notes',
        help='Slicer settings, plate setup, notes for operators',
    )


class PrintRestockOrderLine(models.Model):
    _name = 'print.restock.order.line'
    _description = 'Filament Restock Order Line'
    _order = 'order_id, sequence, id'

    order_id = fields.Many2one(
        'print.restock.order',
        string='Restock Order',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    filament_id = fields.Many2one(
        'print.filament',
        string='Filament',
        required=True,
    )
    qty_ordered = fields.Integer(string='Qty Ordered', default=1)
    qty_received = fields.Integer(string='Qty Received', default=0)
    notes = fields.Char(string='Notes')

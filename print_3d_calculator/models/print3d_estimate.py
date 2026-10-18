import base64
import logging
import math
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import print_file_parser

_logger = logging.getLogger(__name__)

FILE_FORMATS = [
    ('gcode', 'G-code'),
    ('bgcode', 'Binary G-code'),
    ('3mf', '3MF'),
    ('ufp', 'UFP (Cura)'),
    ('stl', 'STL'),
    ('obj', 'OBJ'),
    ('amf', 'AMF'),
]

# Fields whose change means the price has to be worked out again.
PRICING_FIELDS = {'profile_id', 'line_ids', 'print_time_seconds'}


def format_duration(seconds):
    seconds = int(seconds or 0)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = round(rest / 60)
    if minutes == 60:
        hours, minutes = hours + 1, 0
    parts = []
    if days:
        parts.append('%dd' % days)
    if hours or days:
        parts.append('%dh' % hours)
    parts.append('%dm' % minutes)
    return ' '.join(parts)


class Print3dEstimate(models.Model):
    _name = 'print3d.estimate'
    _description = '3D Print Estimate'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True)
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        tracking=True,
        domain=[('print3d_dynamic_pricing', '=', True)],
        help='The 3D printing product this estimate is priced for.',
    )
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product Template',
        index='btree_not_null',
        readonly=True,
        help='Set when this is the reference file attached to a product.',
    )
    profile_id = fields.Many2one(
        'print3d.pricing.profile',
        string='Pricing Profile',
        required=True,
        tracking=True,
        default=lambda self: self._default_profile(),
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    source = fields.Selection(
        [('backend', 'Backend'), ('website', 'Website'), ('product', 'Product')],
        default='backend',
        required=True,
        readonly=True,
    )
    access_token = fields.Char(copy=False, readonly=True, default=lambda self: uuid.uuid4().hex)
    state = fields.Selection(
        [('draft', 'Draft'), ('done', 'Estimated'), ('error', 'Error')],
        string='Status',
        default='draft',
        required=True,
        readonly=True,
        copy=False,
        tracking=True,
    )

    # ── File ─────────────────────────────────────────────────────────────
    file = fields.Binary(string='Print File', attachment=True, copy=False)
    filename = fields.Char(string='File Name', tracking=True)
    file_format = fields.Selection(FILE_FORMATS, string='File Type', readonly=True)
    slicer = fields.Char(string='Slicer', readonly=True)
    sliced = fields.Boolean(
        string='Sliced',
        readonly=True,
        help='Sliced files include the slicer\'s own filament and time figures. '
             'Unsliced models are estimated from their volume using the pricing profile.',
    )
    plate_count = fields.Integer(string='Plates', readonly=True)
    error_message = fields.Text(string='Error', readonly=True)
    warnings = fields.Text(string='Notes', readonly=True)

    # ── Results ──────────────────────────────────────────────────────────
    line_ids = fields.One2many('print3d.estimate.filament', 'estimate_id', string='Filaments', copy=True)
    filament_count = fields.Integer(
        string='Filaments Required', compute='_compute_filament_totals', store=True,
    )
    total_filament_g = fields.Float(
        string='Total Filament (g)', compute='_compute_filament_totals', store=True, digits=(16, 2),
    )
    total_filament_m = fields.Float(
        string='Total Filament (m)', compute='_compute_filament_totals', store=True, digits=(16, 2),
    )
    print_time_seconds = fields.Integer(string='Print Time (s)', readonly=True)
    print_time_hours = fields.Float(
        string='Print Time (h)', compute='_compute_print_time', store=True, digits=(16, 2),
    )
    print_time_display = fields.Char(string='Print Time', compute='_compute_print_time', store=True)
    volume_cm3 = fields.Float(string='Model Volume (cm³)', readonly=True, digits=(16, 2))
    surface_area_cm2 = fields.Float(string='Surface Area (cm²)', readonly=True, digits=(16, 2))
    size_x_mm = fields.Float(string='Width (mm)', readonly=True, digits=(16, 1))
    size_y_mm = fields.Float(string='Depth (mm)', readonly=True, digits=(16, 1))
    size_z_mm = fields.Float(string='Height (mm)', readonly=True, digits=(16, 1))
    project_infill_percent = fields.Float(
        string='Infill in Project (%)', readonly=True,
        help='Infill saved in an unsliced 3MF project, if any.',
    )
    infill_percent = fields.Float(
        string='Infill Used (%)', readonly=True,
        help='Infill assumed for an unsliced model (from the project or the pricing profile).',
    )

    # ── Costing ──────────────────────────────────────────────────────────
    material_cost = fields.Monetary(string='Filament Cost', readonly=True)
    machine_cost = fields.Monetary(string='Printer Time Cost', readonly=True)
    setup_cost = fields.Monetary(string='Setup & Colour Fees', readonly=True)
    cost_total = fields.Monetary(string='Total Cost', readonly=True, tracking=True)
    markup_amount = fields.Monetary(string='Markup', readonly=True)
    price = fields.Monetary(
        string='Price per Print', readonly=True, tracking=True,
        help='Sales price (excluding taxes) for one print of this file.',
    )

    # ── Sales / invoicing ────────────────────────────────────────────────
    sale_line_ids = fields.One2many('sale.order.line', 'print3d_estimate_id', string='Sales Order Lines')
    invoice_line_ids = fields.One2many('account.move.line', 'print3d_estimate_id', string='Invoice Lines')
    sale_order_count = fields.Integer(compute='_compute_sale_invoice_counts')
    invoice_count = fields.Integer(compute='_compute_sale_invoice_counts')
    locked = fields.Boolean(
        compute='_compute_sale_invoice_counts',
        help='Invoiced estimates keep their figures so the invoice stays as recorded.',
    )

    @api.model
    def _default_profile(self, company=None, product=None):
        company = company or self.env.company
        if product and product.print3d_profile_id:
            return product.print3d_profile_id
        return company.print3d_profile_id or self.env['print3d.pricing.profile'].search(
            ['|', ('company_id', '=', False), ('company_id', '=', company.id)], limit=1,
        )

    @api.depends('line_ids.weight_g', 'line_ids.length_m')
    def _compute_filament_totals(self):
        for estimate in self:
            lines = estimate.line_ids.filtered(lambda l: l.weight_g or l.length_m)
            estimate.filament_count = len(lines)
            estimate.total_filament_g = sum(lines.mapped('weight_g'))
            estimate.total_filament_m = sum(lines.mapped('length_m'))

    @api.depends('print_time_seconds')
    def _compute_print_time(self):
        for estimate in self:
            estimate.print_time_hours = estimate.print_time_seconds / 3600.0
            estimate.print_time_display = (
                format_duration(estimate.print_time_seconds) if estimate.print_time_seconds else ''
            )

    @api.depends('sale_line_ids', 'invoice_line_ids.parent_state')
    def _compute_sale_invoice_counts(self):
        for estimate in self:
            estimate.sale_order_count = len(estimate.sale_line_ids.order_id)
            moves = estimate.invoice_line_ids.move_id
            estimate.invoice_count = len(moves)
            estimate.locked = bool(moves.filtered(lambda m: m.state != 'cancel'))

    # ─────────────────────────────────────────────────────────────────────
    # CRUD
    # ─────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('print3d.estimate') or _('New')
            if not vals.get('profile_id'):
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                product = self.env['product.product'].browse(vals.get('product_id'))
                vals['profile_id'] = self._default_profile(company, product).id
        estimates = super().create(vals_list)
        estimates.filtered('file')._analyse()
        return estimates

    def write(self, vals):
        if self.filtered('locked') and (PRICING_FIELDS | {'file'}) & set(vals):
            raise UserError(_(
                'This estimate has been invoiced, so its file and costing can no longer change. '
                'Duplicate it to price a new version.'
            ))
        res = super().write(vals)
        if vals.get('file'):
            self._analyse()
        elif 'file' in vals:
            self._reset_results()
        elif PRICING_FIELDS & set(vals) and not self.env.context.get('print3d_no_reprice'):
            self._update_pricing()
        return res

    def copy_data(self, default=None):
        vals_list = super().copy_data(default)
        for estimate, vals in zip(self, vals_list):
            # The file is not copied by the ORM (copy=False): copy it so the
            # duplicate can be re-analysed and priced on its own.
            vals.setdefault('file', estimate.file)
        return vals_list

    # ─────────────────────────────────────────────────────────────────────
    # Analysis
    # ─────────────────────────────────────────────────────────────────────

    def _reset_results(self):
        self.with_context(print3d_no_reprice=True).write({
            'state': 'draft',
            'line_ids': [fields.Command.clear()],
            'file_format': False,
            'slicer': False,
            'sliced': False,
            'plate_count': 0,
            'print_time_seconds': 0,
            'volume_cm3': 0.0,
            'surface_area_cm2': 0.0,
            'size_x_mm': 0.0,
            'size_y_mm': 0.0,
            'size_z_mm': 0.0,
            'error_message': False,
            'warnings': False,
            'material_cost': 0.0,
            'machine_cost': 0.0,
            'setup_cost': 0.0,
            'cost_total': 0.0,
            'markup_amount': 0.0,
            'price': 0.0,
        })

    def _analyse(self):
        """Read the attached file and fill in filaments, time and price."""
        materials = self.env['print3d.material'].search([])
        for estimate in self:
            if not estimate.file:
                estimate._reset_results()
                continue
            try:
                data = base64.b64decode(estimate.with_context(bin_size=False).file)
                analysis = print_file_parser.analyse(data, estimate.filename or '')
            except print_file_parser.PrintFileError as e:
                estimate._reset_results()
                estimate.with_context(print3d_no_reprice=True).write({
                    'state': 'error', 'error_message': str(e),
                })
                continue
            except Exception as e:  # noqa: BLE001 - a broken upload must not crash the form
                _logger.exception('Could not analyse 3D print file %s', estimate.filename)
                estimate._reset_results()
                estimate.with_context(print3d_no_reprice=True).write({
                    'state': 'error',
                    'error_message': _('The file could not be read: %s', e),
                })
                continue
            estimate._apply_analysis(analysis, materials)
        self._update_pricing()

    def _apply_analysis(self, analysis, materials):
        self.ensure_one()
        default_material = self.profile_id.default_material_id
        lines = []
        for sequence, filament in enumerate(analysis.filaments, start=1):
            material = materials._find_for_slicer_name(filament.material, materials) or default_material
            lines.append(fields.Command.create({
                'sequence': sequence,
                'slot': filament.slot,
                'slicer_material': filament.material or filament.name,
                'colour': filament.colour or (material.colour if material else False),
                'material_id': material.id,
                'length_m': filament.length_mm / 1000.0,
                'weight_g': filament.weight_g,
                'volume_cm3': filament.volume_cm3,
                'slicer_weight': filament.weight_reported,
                'slicer_density': filament.density,
                'mesh_volume_cm3': filament.mesh_volume_cm3,
                'mesh_area_cm2': filament.mesh_area_cm2,
            }))
        size = analysis.size_mm or (0.0, 0.0, 0.0)
        self.with_context(print3d_no_reprice=True).write({
            'state': 'done',
            'line_ids': [fields.Command.clear()] + lines,
            'file_format': analysis.file_format,
            'slicer': analysis.slicer,
            'sliced': analysis.sliced,
            'plate_count': analysis.plate_count,
            'print_time_seconds': analysis.print_time_s,
            'volume_cm3': analysis.volume_cm3,
            'surface_area_cm2': analysis.surface_area_cm2,
            'size_x_mm': size[0],
            'size_y_mm': size[1],
            'size_z_mm': size[2],
            'project_infill_percent': analysis.settings.get('infill_percent', 0.0),
            'error_message': False,
            'warnings': '\n'.join(analysis.warnings) or False,
        })

    def action_analyse(self):
        if self.filtered('locked'):
            raise UserError(_('Invoiced estimates cannot be re-analysed. Duplicate it instead.'))
        if not self.filtered('file'):
            raise UserError(_('Attach a 3D print file first.'))
        self._analyse()
        return True

    # ─────────────────────────────────────────────────────────────────────
    # Pricing
    # ─────────────────────────────────────────────────────────────────────

    def _estimate_unsliced(self):
        """Filament weight and time for a model that was never sliced."""
        self.ensure_one()
        profile = self.profile_id
        infill = profile.infill_percent
        if profile.use_project_settings and self.project_infill_percent:
            infill = self.project_infill_percent
        shell_cm = (profile.wall_thickness_mm or 0.0) / 10.0
        total_volume_cm3 = 0.0
        for line in self.line_ids:
            volume = line.mesh_volume_cm3
            shell = min(volume, line.mesh_area_cm2 * shell_cm)
            plastic = (shell + (volume - shell) * infill / 100.0) * (1 + profile.support_percent / 100.0)
            area_mm2 = math.pi * (print_file_parser.DEFAULT_DIAMETER / 2.0) ** 2
            line.with_context(print3d_no_reprice=True).write({
                'volume_cm3': plastic,
                'weight_g': plastic * line._density(),
                'length_m': plastic * 1000.0 / area_mm2 / 1000.0,
            })
            total_volume_cm3 += plastic
        seconds = 0
        if total_volume_cm3 and profile.volumetric_speed:
            seconds = total_volume_cm3 * 1000.0 / profile.volumetric_speed
            seconds += (profile.time_overhead_minutes or 0.0) * 60.0
        return int(round(seconds)), infill

    def _update_pricing(self):
        for estimate in self:
            if estimate.state != 'done' or not estimate.profile_id or estimate.locked:
                continue
            profile = estimate.profile_id
            values = {}
            if not estimate.sliced:
                values['print_time_seconds'], values['infill_percent'] = estimate._estimate_unsliced()
            else:
                # Slicers that only report length / volume (e.g. Cura): weigh
                # the filament with the chosen material's density.
                for line in estimate.line_ids.filtered(lambda l: l.volume_cm3 and not l.slicer_weight):
                    line.with_context(print3d_no_reprice=True).weight_g = line.volume_cm3 * line._density()
            currency = estimate.currency_id
            company = estimate.company_id
            date = fields.Date.context_today(estimate)
            material_cost = 0.0
            for line in estimate.line_ids:
                cost_per_kg = line.material_id._get_cost_per_kg() if line.material_id else 0.0
                if line.material_id and line.material_id.currency_id != currency:
                    cost_per_kg = line.material_id.currency_id._convert(cost_per_kg, currency, company, date)
                cost = line.weight_g / 1000.0 * cost_per_kg * (1 + profile.waste_percent / 100.0)
                line.with_context(print3d_no_reprice=True).write({
                    'cost_per_kg': cost_per_kg,
                    'cost': cost,
                })
                material_cost += cost
            hours = values.get('print_time_seconds', estimate.print_time_seconds) / 3600.0
            rate = profile.currency_id._convert(profile.machine_rate_per_hour, currency, company, date)
            setup = profile.currency_id._convert(profile.setup_fee, currency, company, date)
            extra_fee = profile.currency_id._convert(profile.extra_filament_fee, currency, company, date)
            minimum = profile.currency_id._convert(profile.minimum_price, currency, company, date)
            used = estimate.line_ids.filtered(lambda l: l.weight_g or l.length_m)
            machine_cost = hours * rate
            setup_cost = setup + max(len(used) - 1, 0) * extra_fee
            cost_total = material_cost + machine_cost + setup_cost
            markup = cost_total * profile.markup_percent / 100.0
            price = max(cost_total + markup, minimum)
            values.update({
                'material_cost': currency.round(material_cost),
                'machine_cost': currency.round(machine_cost),
                'setup_cost': currency.round(setup_cost),
                'cost_total': currency.round(cost_total),
                'markup_amount': currency.round(price - cost_total),
                'price': currency.round(price),
            })
            estimate.with_context(print3d_no_reprice=True).write(values)

    def action_update_pricing(self):
        if self.filtered('locked'):
            raise UserError(_('Invoiced estimates keep their recorded costing.'))
        self._update_pricing()
        return True

    # ─────────────────────────────────────────────────────────────────────
    # Sales
    # ─────────────────────────────────────────────────────────────────────

    def _sale_line_description(self):
        """Text recorded on the sales order / invoice line."""
        self.ensure_one()
        parts = [_('3D print: %s', self.filename or self.name)]
        materials = ', '.join(
            '%s %.1f g' % (line.material_id.name or line.slicer_material or _('Filament'), line.weight_g)
            for line in self.line_ids
        )
        if materials:
            parts.append(_('%(count)s filament(s): %(materials)s', count=self.filament_count, materials=materials))
        summary = []
        if self.total_filament_g:
            summary.append(_('Total %.1f g', self.total_filament_g))
        if self.print_time_display:
            summary.append(_('Print time %s', self.print_time_display))
        if summary:
            parts.append(' · '.join(summary))
        parts.append(_('Estimate %s', self.name))
        return '\n'.join(parts)

    def action_create_quotation(self):
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('The file has to be estimated before it can be quoted.'))
        product = self.product_id or self.env['product.product'].search(
            [('print3d_dynamic_pricing', '=', True), ('sale_ok', '=', True)], limit=1,
        )
        if not product:
            raise UserError(_(
                'Choose a product with "3D Print Dynamic Pricing" enabled on the estimate first.'
            ))
        order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id or self.env.user.partner_id.id,
            'company_id': self.company_id.id,
            'order_line': [fields.Command.create({
                'product_id': product.id,
                'product_uom_qty': 1.0,
                'print3d_estimate_id': self.id,
                'name': '%s\n%s' % (product.display_name, self._sale_line_description()),
            })],
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
        }

    def action_view_sale_orders(self):
        self.ensure_one()
        orders = self.sale_line_ids.order_id
        action = self.env['ir.actions.act_window']._for_xml_id('sale.action_quotations_with_onboarding')
        action.update({'domain': [('id', 'in', orders.ids)], 'context': {}})
        if len(orders) == 1:
            action.update({'view_mode': 'form', 'views': [(False, 'form')], 'res_id': orders.id})
        return action

    def action_view_invoices(self):
        self.ensure_one()
        moves = self.invoice_line_ids.move_id
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_out_invoice_type')
        action.update({'domain': [('id', 'in', moves.ids)], 'context': {}})
        if len(moves) == 1:
            action.update({'view_mode': 'form', 'views': [(False, 'form')], 'res_id': moves.id})
        return action

    @api.model
    def _gc_website_estimates(self):
        """Remove website uploads that never made it into a cart."""
        limit = fields.Datetime.subtract(fields.Datetime.now(), days=7)
        self.sudo().search([
            ('source', '=', 'website'),
            ('sale_line_ids', '=', False),
            ('create_date', '<', limit),
        ]).unlink()


class Print3dEstimateFilament(models.Model):
    _name = 'print3d.estimate.filament'
    _description = '3D Print Estimate Filament'
    _order = 'estimate_id, sequence, id'

    estimate_id = fields.Many2one('print3d.estimate', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='estimate_id.company_id', store=True)
    currency_id = fields.Many2one(related='estimate_id.currency_id')
    sequence = fields.Integer(default=10)
    slot = fields.Integer(string='Slot', help='Extruder / AMS slot number in the print file.')
    slicer_material = fields.Char(string='Filament in File')
    colour = fields.Char(string='Colour')
    material_id = fields.Many2one('print3d.material', string='Material')
    length_m = fields.Float(string='Length (m)', digits=(16, 2))
    weight_g = fields.Float(string='Weight (g)', digits=(16, 2))
    volume_cm3 = fields.Float(string='Filament Volume (cm³)', digits=(16, 4))
    slicer_weight = fields.Boolean(
        string='Weight from Slicer',
        help='The slicer reported this weight. Otherwise it is worked out from '
             'the filament volume and the material density.',
    )
    slicer_density = fields.Float(string='Density in File', digits=(16, 3))
    mesh_volume_cm3 = fields.Float(string='Model Volume (cm³)', digits=(16, 2))
    mesh_area_cm2 = fields.Float(string='Model Surface (cm²)', digits=(16, 2))
    cost_per_kg = fields.Monetary(string='Cost per kg', readonly=True)
    cost = fields.Monetary(string='Cost', readonly=True)

    def _density(self):
        self.ensure_one()
        return self.material_id.density or self.slicer_density or print_file_parser.DEFAULT_DENSITY

    def write(self, vals):
        if not self.env.context.get('print3d_no_reprice') and {'material_id', 'weight_g', 'length_m'} & set(vals):
            if self.estimate_id.filtered('locked'):
                raise UserError(_('This estimate has been invoiced, so its filaments can no longer change.'))
        res = super().write(vals)
        if not self.env.context.get('print3d_no_reprice') and {'material_id', 'weight_g', 'length_m'} & set(vals):
            self.estimate_id._update_pricing()
        return res

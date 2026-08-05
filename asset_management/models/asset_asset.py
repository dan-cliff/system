# -*- coding: utf-8 -*-
import base64
import uuid
from io import BytesIO

from odoo import api, fields, models


class Asset(models.Model):
    _name = 'asset.asset'
    _description = 'Asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'asset_number desc'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(string='Asset Name', required=True, tracking=True)
    asset_number = fields.Char(
        string='Asset #',
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('asset.asset') or 'New',
    )
    image = fields.Image('Photo', max_width=1024, max_height=1024)
    serial_number = fields.Char(string='Serial / VIN', tracking=True)
    registration_number = fields.Char(string='Registration Number', tracking=True)
    purchase_date = fields.Date(string='Purchase Date', tracking=True)
    location = fields.Char(string='Location', tracking=True)
    state = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('maintenance', 'Under Maintenance'),
            ('inactive', 'Inactive'),
            ('retired', 'Retired'),
        ],
        string='Status',
        default='active',
        required=True,
        tracking=True,
    )
    notes = fields.Html(string='Notes')

    # ── Purchase Information ──────────────────────────────────────────────────
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        domain=[('is_company', '=', True)],
        ondelete='set null',
        tracking=True,
    )
    manufacturer_id = fields.Many2one(
        'res.partner',
        string='Manufacturer',
        domain=[('is_company', '=', True)],
        ondelete='set null',
        tracking=True,
    )
    purchase_cost = fields.Monetary(
        string='Purchase Cost',
        currency_field='currency_id',
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    warranty_expiry_date = fields.Date(string='Warranty Expiry', tracking=True)

    # ── Ownership & Assignment ────────────────────────────────────────────────
    owner_id = fields.Many2one(
        'res.partner',
        string='Owner',
        ondelete='set null',
        tracking=True,
        help='The person or company that owns this asset.',
    )
    assigned_to_id = fields.Many2one(
        'hr.employee',
        string='Assigned To',
        ondelete='set null',
        tracking=True,
        help='The employee currently responsible for this asset.',
    )
    date_assignment = fields.Date(string='Date of Assignment', tracking=True)

    # ── Usage Unit ────────────────────────────────────────────────────────────
    usage_unit_id = fields.Many2one(
        'asset.usage.unit',
        string='Usage Unit',
        ondelete='set null',
        tracking=True,
        help='The unit used for usage readings on this asset. '
             'Automatically inherited from the Sub-Type, then the Type. '
             'Editable only when neither the Type nor Sub-Type has a unit defined.',
    )
    usage_unit_locked = fields.Boolean(
        string='Usage Unit Locked',
        compute='_compute_usage_unit_locked',
        help='True when the usage unit is inherited from the Type or Sub-Type.',
    )
    usage_unit_short_code = fields.Char(
        related='usage_unit_id.short_code',
        string='Unit Short Code',
        store=False,
    )

    @api.depends('asset_type_id.usage_unit_id', 'asset_subtype_id.usage_unit_id')
    def _compute_usage_unit_locked(self):
        for rec in self:
            rec.usage_unit_locked = bool(
                rec.asset_subtype_id.usage_unit_id or rec.asset_type_id.usage_unit_id
            )

    # ── Classification ────────────────────────────────────────────────────────
    asset_type_id = fields.Many2one(
        'asset.type',
        string='Asset Type',
        required=True,
        tracking=True,
        ondelete='restrict',
    )
    asset_subtype_id = fields.Many2one(
        'asset.subtype',
        string='Asset Sub-Type',
        domain="[('asset_type_id', '=', asset_type_id)]",
        tracking=True,
        ondelete='restrict',
    )

    # ── Effective Feature Flags (union of type + subtype) ─────────────────────
    eff_maintenance = fields.Boolean(
        string='Maintenance Enabled',
        compute='_compute_features',
        store=True,
    )
    eff_usage_tracking = fields.Boolean(
        string='Usage Tracking Enabled',
        compute='_compute_features',
        store=True,
    )
    eff_risk_assessments = fields.Boolean(
        string='Risk Assessments Enabled',
        compute='_compute_features',
        store=True,
    )
    eff_hazardous = fields.Boolean(
        string='Hazardous Chemicals Enabled',
        compute='_compute_features',
        store=True,
    )
    eff_project = fields.Boolean(
        string='Project Assignment Enabled',
        compute='_compute_features',
        store=True,
    )
    eff_location_tracking = fields.Boolean(
        string='Location Tracking Enabled',
        compute='_compute_features',
        store=True,
    )
    eff_software = fields.Boolean(
        string='Software Fields Enabled',
        compute='_compute_features',
        store=True,
    )

    @api.depends(
        'asset_type_id.has_maintenance',
        'asset_type_id.has_usage_tracking',
        'asset_type_id.has_risk_assessments',
        'asset_type_id.has_hazardous',
        'asset_type_id.has_project',
        'asset_type_id.has_location_tracking',
        'asset_type_id.has_software',
        'asset_subtype_id.has_maintenance',
        'asset_subtype_id.has_usage_tracking',
        'asset_subtype_id.has_risk_assessments',
        'asset_subtype_id.has_hazardous',
        'asset_subtype_id.has_project',
        'asset_subtype_id.has_location_tracking',
        'asset_subtype_id.has_software',
    )
    def _compute_features(self):
        for rec in self:
            t = rec.asset_type_id
            s = rec.asset_subtype_id
            rec.eff_maintenance = (t.has_maintenance or s.has_maintenance)
            rec.eff_usage_tracking = (t.has_usage_tracking or s.has_usage_tracking)
            rec.eff_risk_assessments = (t.has_risk_assessments or s.has_risk_assessments)
            rec.eff_hazardous = (t.has_hazardous or s.has_hazardous)
            rec.eff_project = (t.has_project or s.has_project)
            rec.eff_location_tracking = (t.has_location_tracking or s.has_location_tracking)
            rec.eff_software = (t.has_software or s.has_software)

    # ── Software Details ──────────────────────────────────────────────────────
    sw_supplier_id = fields.Many2one(
        'res.partner',
        string='Software Supplier',
        domain=[('is_company', '=', True)],
        ondelete='set null',
        help='Software supplier or vendor (companies only).',
    )
    sw_website = fields.Char(string='Software Website')
    sw_licence_key = fields.Char(string='Licence Key')
    sw_notes = fields.Text(string='Software Notes')

    # ── Location ──────────────────────────────────────────────────────────────
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))
    location_updated = fields.Datetime(string='Location Updated', readonly=True)
    location_accuracy = fields.Float(string='Accuracy (m)', digits=(10, 2))
    nearest_address = fields.Char(string='Nearest Street Address', readonly=True)

    location_log_ids = fields.One2many('asset.location.log', 'asset_id', string='Location History')
    location_log_count = fields.Integer(compute='_compute_counts')

    map_embed = fields.Html(
        string='Map',
        compute='_compute_map_embed',
        sanitize=False,
        store=False,
    )

    @api.depends('latitude', 'longitude')
    def _compute_map_embed(self):
        for rec in self:
            if rec.latitude and rec.longitude:
                lat, lon = rec.latitude, rec.longitude
                delta = 0.005
                bbox = f'{lon - delta},{lat - delta},{lon + delta},{lat + delta}'
                url = (
                    f'https://www.openstreetmap.org/export/embed.html'
                    f'?bbox={bbox}&layer=mapnik&marker={lat},{lon}'
                )
                rec.map_embed = (
                    f'<iframe src="{url}" style="width:100%;height:280px;'
                    f'border:1px solid #dee2e6;border-radius:8px;" '
                    f'allowfullscreen loading="lazy"></iframe>'
                )
            else:
                rec.map_embed = ''

    # ── Usage Tracking ────────────────────────────────────────────────────────
    usage_log_ids = fields.One2many('asset.usage.log', 'asset_id', string='Usage Logs')
    usage_log_count = fields.Integer(compute='_compute_counts')

    latest_usage_reading = fields.Float(
        string='Latest Reading',
        compute='_compute_latest_usage',
        store=True,
        digits=(16, 2),
    )
    latest_usage_date = fields.Date(
        string='Latest Reading Date',
        compute='_compute_latest_usage',
        store=True,
    )
    latest_usage_unit = fields.Char(
        string='Unit',
        compute='_compute_latest_usage',
        store=True,
    )

    @api.depends('usage_log_ids.reading', 'usage_log_ids.date', 'usage_log_ids.unit')
    def _compute_latest_usage(self):
        for rec in self:
            latest = rec.usage_log_ids.sorted(key=lambda r: (r.date or fields.Date.min, r.id), reverse=True)[:1]
            if latest:
                rec.latest_usage_reading = latest.reading
                rec.latest_usage_date = latest.date
                rec.latest_usage_unit = latest.unit
            else:
                rec.latest_usage_reading = 0.0
                rec.latest_usage_date = False
                rec.latest_usage_unit = ''

    # ── Defects ───────────────────────────────────────────────────────────────
    defect_ids = fields.One2many('asset.defect', 'asset_id', string='Defect Reports')
    defect_count = fields.Integer(compute='_compute_counts')
    open_defect_count = fields.Integer(compute='_compute_counts')

    # ── Maintenance Logs ──────────────────────────────────────────────────────
    maintenance_log_ids = fields.One2many('asset.maintenance.log', 'asset_id', string='Maintenance Logs')
    maintenance_log_count = fields.Integer(compute='_compute_counts')

    @api.depends('usage_log_ids', 'defect_ids', 'maintenance_log_ids', 'location_log_ids')
    def _compute_counts(self):
        for rec in self:
            rec.usage_log_count = len(rec.usage_log_ids)
            rec.defect_count = len(rec.defect_ids)
            rec.open_defect_count = len(rec.defect_ids.filtered(lambda d: d.state in ('open', 'in_progress')))
            rec.maintenance_log_count = len(rec.maintenance_log_ids)
            rec.location_log_count = len(rec.location_log_ids)

    # ── Control Plane (PWA) ───────────────────────────────────────────────────
    cp_token = fields.Char(
        string='Control Plane Token',
        copy=False,
        readonly=True,
        index=True,
    )
    cp_url = fields.Char(
        string='Control Plane URL',
        compute='_compute_cp_url',
    )
    cp_qr_code = fields.Binary(
        string='QR Code',
        compute='_compute_cp_qr_code',
        store=False,
    )

    @api.depends('cp_token')
    def _compute_cp_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for rec in self:
            if rec.cp_token:
                rec.cp_url = f'{base}/asset/cp/{rec.cp_token}'
            else:
                rec.cp_url = ''

    @api.depends('cp_url')
    def _compute_cp_qr_code(self):
        try:
            import qrcode
        except ImportError:
            for rec in self:
                rec.cp_qr_code = False
            return
        for rec in self:
            if not rec.cp_url:
                rec.cp_qr_code = False
                continue
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(rec.cp_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color='#0f172a', back_color='white')
            buf = BytesIO()
            img.save(buf, format='PNG')
            rec.cp_qr_code = base64.b64encode(buf.getvalue())

    # ── ORM overrides ─────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('asset_number', 'New') == 'New':
                vals['asset_number'] = self.env['ir.sequence'].next_by_code('asset.asset') or 'New'
        return super().create(vals_list)

    @api.onchange('asset_type_id')
    def _onchange_asset_type(self):
        """Clear sub-type when type changes and inherit usage unit from the new type."""
        if self.asset_subtype_id and self.asset_subtype_id.asset_type_id != self.asset_type_id:
            self.asset_subtype_id = False
        # Inherit unit from type (subtype onchange will override if subtype is set)
        if self.asset_type_id and self.asset_type_id.usage_unit_id:
            self.usage_unit_id = self.asset_type_id.usage_unit_id
        elif not self.asset_subtype_id:
            # Type has no unit and no subtype — allow manual entry (don't clear an
            # existing manual value unless the user explicitly changes it)
            pass

    @api.onchange('asset_subtype_id')
    def _onchange_asset_subtype(self):
        """Inherit usage unit from sub-type (takes priority over type)."""
        if self.asset_subtype_id and self.asset_subtype_id.usage_unit_id:
            self.usage_unit_id = self.asset_subtype_id.usage_unit_id
        elif self.asset_type_id and self.asset_type_id.usage_unit_id:
            # Sub-type has no unit — fall back to type's unit
            self.usage_unit_id = self.asset_type_id.usage_unit_id

    def action_generate_token(self):
        """Regenerate the control plane token (invalidates old links)."""
        self.ensure_one()
        self.cp_token = str(uuid.uuid4())

    def action_view_cp_details(self):
        """Open the Control Plane details popup."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Control Plane — {self.name}',
            'res_model': 'asset.asset',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('asset_management.view_asset_cp_details_popup').id, 'form')],
            'target': 'new',
        }

    # ── Smart button actions ──────────────────────────────────────────────────
    def action_view_usage_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Usage Logs',
            'res_model': 'asset.usage.log',
            'view_mode': 'list,form',
            'domain': [('asset_id', '=', self.id)],
            'context': {'default_asset_id': self.id},
        }

    def action_view_defects(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Defect Reports',
            'res_model': 'asset.defect',
            'view_mode': 'list,form',
            'domain': [('asset_id', '=', self.id)],
            'context': {'default_asset_id': self.id},
        }

    def action_view_maintenance_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Maintenance Logs',
            'res_model': 'asset.maintenance.log',
            'view_mode': 'list,form',
            'domain': [('asset_id', '=', self.id)],
            'context': {'default_asset_id': self.id},
        }

    def action_view_location_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Location History',
            'res_model': 'asset.location.log',
            'view_mode': 'list,form',
            'domain': [('asset_id', '=', self.id)],
            'context': {'default_asset_id': self.id},
        }

    def action_view_management_features(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Management Features — {self.name}',
            'res_model': 'asset.asset',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('asset_management.view_asset_management_features_popup').id, 'form')],
            'target': 'new',
        }

    def action_view_current_location(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Current Location — {self.name}',
            'res_model': 'asset.asset',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('asset_management.view_asset_location_popup').id, 'form')],
            'target': 'new',
        }

    def action_open_control_plane(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.cp_url,
            'target': 'new',
        }

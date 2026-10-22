from odoo import api, fields, models


class Print3dPricingProfile(models.Model):
    _name = 'print3d.pricing.profile'
    _description = '3D Print Pricing Profile'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        help='Leave empty to use this profile in every company.',
    )
    currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_currency_id',
    )
    default_material_id = fields.Many2one(
        'print3d.material',
        string='Default Material',
        help='Used for filaments whose type does not match any material.',
    )

    # ── Costs ────────────────────────────────────────────────────────────
    machine_rate_per_hour = fields.Monetary(
        string='Printer Rate per Hour',
        default=1.5,
        help='Machine time: power, wear and depreciation per hour of printing.',
    )
    setup_fee = fields.Monetary(
        string='Setup Fee',
        help='Added once per print job (preparation, plate removal, clean-up).',
    )
    extra_filament_fee = fields.Monetary(
        string='Fee per Extra Filament',
        help='Added for every filament after the first (colour / material changes).',
    )
    waste_percent = fields.Float(
        string='Waste (%)',
        default=5.0,
        help='Extra filament allowed for purging, brims and failed starts.',
    )
    markup_percent = fields.Float(
        string='Markup (%)',
        default=50.0,
        help='Added on top of the total cost to give the price.',
    )
    minimum_price = fields.Monetary(
        string='Minimum Price',
        help='The price is never lower than this.',
    )

    # ── Estimating unsliced models (STL / OBJ / 3MF that was not sliced) ─
    infill_percent = fields.Float(
        string='Infill (%)',
        default=15.0,
        help='Infill used to estimate filament for models that have not been sliced.',
    )
    wall_thickness_mm = fields.Float(
        string='Shell Thickness (mm)',
        default=1.2,
        help='Combined thickness of walls / top / bottom layers for unsliced models.',
    )
    support_percent = fields.Float(
        string='Supports (%)',
        default=10.0,
        help='Extra filament allowed for supports on unsliced models.',
    )
    volumetric_speed = fields.Float(
        string='Average Print Speed (mm³/s)',
        default=8.0,
        help='Average plastic flow, used to estimate the print time of unsliced models.',
    )
    time_overhead_minutes = fields.Float(
        string='Time Overhead (min)',
        default=5.0,
        help='Heating, levelling and purging time added to unsliced estimates.',
    )
    use_project_settings = fields.Boolean(
        string='Use Project Infill',
        default=True,
        help='When a 3MF project includes its own infill setting, use it instead of the infill above.',
    )

    @api.depends('company_id')
    def _compute_currency_id(self):
        for profile in self:
            profile.currency_id = (profile.company_id or self.env.company).currency_id

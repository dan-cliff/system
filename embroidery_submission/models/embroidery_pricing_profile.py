# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EmbroideryPricingProfile(models.Model):
    """How a submitted design is costed out."""
    _name = 'embroidery.pricing.profile'
    _description = 'Embroidery Pricing Profile'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        help='Leave empty to use this profile in every company.',
    )
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id')

    # ── Costs ─────────────────────────────────────────────────────────────
    price_per_thousand_stitches = fields.Monetary(
        string='Cost per 1,000 Stitches',
        default=0.40,
        help='Thread, needles and backing used per 1,000 stitches.',
    )
    color_change_fee = fields.Monetary(
        string='Fee per Colour Change',
        default=0.30,
        help='Added for every colour change in the design (threading and thread changes).',
    )
    machine_rate_per_hour = fields.Monetary(
        string='Machine Rate per Hour',
        default=15.0,
        help='Machine and operator time per hour of the estimated duration.',
    )
    setup_fee = fields.Monetary(
        string='Setup Fee',
        default=2.0,
        help='Added once per piece (hooping, trimming and finishing).',
    )
    markup_percent = fields.Float(
        string='Markup (%)',
        default=40.0,
        help='Added on top of the total cost to give the price.',
    )
    minimum_price = fields.Monetary(
        string='Minimum Price',
        default=5.0,
        help='The price per piece is never lower than this.',
    )

    # ── Time ──────────────────────────────────────────────────────────────
    color_change_seconds = fields.Integer(
        string='Time per Colour Change (s)',
        default=15,
        help='Added to the estimated duration for every colour change. The stitching time '
             'comes from "Estimate duration based on stitches" in Settings.',
    )
    hooping_minutes = fields.Float(
        string='Hooping Time per Piece (min)',
        default=2.0,
        help='Hooping, loading and unloading time added to the estimated duration.',
    )

    @api.depends('company_id')
    def _compute_currency_id(self):
        for profile in self:
            profile.currency_id = (profile.company_id or self.env.company).currency_id

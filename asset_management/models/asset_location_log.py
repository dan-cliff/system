# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AssetLocationLog(models.Model):
    _name = 'asset.location.log'
    _description = 'Asset Location Log'
    _order = 'recorded_at desc'
    _rec_name = 'recorded_at'

    asset_id = fields.Many2one(
        'asset.asset',
        string='Asset',
        required=True,
        ondelete='cascade',
        index=True,
    )
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))
    accuracy = fields.Float(string='Accuracy (m)', digits=(10, 2))
    recorded_at = fields.Datetime(
        string='Recorded At',
        default=fields.Datetime.now,
        required=True,
    )
    source = fields.Char(string='Source', default='control_plane')
    nearest_address = fields.Char(string='Nearest Street Address', readonly=True)

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
                delta = 0.003
                bbox = f'{lon - delta},{lat - delta},{lon + delta},{lat + delta}'
                url = (
                    f'https://www.openstreetmap.org/export/embed.html'
                    f'?bbox={bbox}&layer=mapnik&marker={lat},{lon}'
                )
                rec.map_embed = (
                    f'<iframe src="{url}" '
                    f'style="width:100%;height:320px;border:1px solid #dee2e6;'
                    f'border-radius:8px;display:block;" '
                    f'allowfullscreen loading="lazy"></iframe>'
                )
            else:
                rec.map_embed = ''

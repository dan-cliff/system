# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .design_mixin import LOCATION_TARGETS


def _location_sign():
    """A 1920 x 1080 sign for a room, aisle, shelf or tote."""
    return [
        {'id': 'band', 'type': 'shape', 'x': 0, 'y': 0, 'w': 1920, 'h': 140, 'fill': 'company_primary'},
        {'id': 'logo', 'type': 'image', 'source': 'company_logo', 'x': 40, 'y': 25, 'w': 300, 'h': 90, 'fit': 'contain'},
        {'id': 'clock', 'type': 'clock', 'format': 'time', 'x': 1520, 'y': 25, 'w': 360, 'h': 90,
         'size': 64, 'bold': True, 'color': '#FFFFFF', 'align': 'right'},
        {'id': 'code', 'type': 'text', 'text': '{{ layout_code }}', 'x': 60, 'y': 190, 'w': 760, 'h': 420,
         'size': 300, 'bold': True, 'color': '#2A3F8F', 'align': 'center'},
        {'id': 'name', 'type': 'text', 'text': '{{ complete_name }}', 'x': 60, 'y': 620, 'w': 760, 'h': 120,
         'size': 48, 'color': '#5B3DB8', 'align': 'center'},
        {'id': 'qr', 'type': 'qr', 'value': '{{ barcode }}', 'x': 290, 'y': 770, 'w': 260, 'h': 260},
        {'id': 'panel', 'type': 'shape', 'x': 880, 'y': 190, 'w': 980, 'h': 840, 'fill': '#F2F2FA', 'radius': 32},
        {'id': 'stock_title', 'type': 'text', 'text': 'In this location', 'x': 920, 'y': 210, 'w': 900, 'h': 80,
         'size': 44, 'bold': True, 'color': '#2A3F8F'},
        {'id': 'stock', 'type': 'stock_list', 'rows': 10, 'x': 920, 'y': 300, 'w': 900, 'h': 700,
         'size': 38, 'color': '#2A3F8F', 'line_color': '#A9ABDC'},
    ]


def _warehouse_sign():
    return [
        {'id': 'band', 'type': 'shape', 'x': 0, 'y': 0, 'w': 1920, 'h': 1080, 'fill': 'company_primary'},
        {'id': 'logo', 'type': 'image', 'source': 'company_logo', 'x': 660, 'y': 120, 'w': 600, 'h': 220, 'fit': 'contain'},
        {'id': 'name', 'type': 'text', 'text': '{{ name }}', 'x': 160, 'y': 400, 'w': 1600, 'h': 220,
         'size': 150, 'bold': True, 'color': '#FFFFFF', 'align': 'center'},
        {'id': 'clock', 'type': 'clock', 'format': 'datetime', 'x': 460, 'y': 660, 'w': 1000, 'h': 120,
         'size': 72, 'color': '#F2F2FA', 'align': 'center'},
        {'id': 'qr', 'type': 'qr', 'value': '{{ inventory_barcode }}', 'x': 1660, 'y': 820, 'w': 200, 'h': 200,
         'background': '#FFFFFF'},
    ]


def _product_sign():
    return [
        {'id': 'picture', 'type': 'image', 'source': 'record_image', 'x': 80, 'y': 140, 'w': 800, 'h': 800, 'fit': 'contain'},
        {'id': 'name', 'type': 'text', 'text': '{{ display_name }}', 'x': 960, 'y': 140, 'w': 880, 'h': 300,
         'size': 80, 'bold': True, 'color': '#2A3F8F'},
        {'id': 'title', 'type': 'text', 'text': 'Where to find it', 'x': 960, 'y': 470, 'w': 880, 'h': 80,
         'size': 44, 'bold': True, 'color': '#5B3DB8'},
        {'id': 'stock', 'type': 'stock_list', 'rows': 6, 'x': 960, 'y': 560, 'w': 880, 'h': 420,
         'size': 38, 'color': '#2A3F8F', 'line_color': '#A9ABDC'},
    ]


def default_sign_layout(target, width=1920.0, height=1080.0):
    """The starting layout of a sign, scaled from 1920 x 1080 to the page."""
    if target in LOCATION_TARGETS:
        layout = _location_sign()
    elif target == 'warehouse':
        layout = _warehouse_sign()
    else:
        layout = _product_sign()
    sx, sy = (width or 1920.0) / 1920.0, (height or 1080.0) / 1080.0
    if sx == 1 and sy == 1:
        return layout
    scale = min(sx, sy)
    for element in layout:
        element.update(x=round(element['x'] * sx), y=round(element['y'] * sy),
                       w=round(element['w'] * sx), h=round(element['h'] * sy))
        for key in ('size', 'radius'):
            if element.get(key):
                element[key] = round(element[key] * scale)
    return layout


class AdvancedInventorySignTemplate(models.Model):
    _name = 'advanced.inventory.sign.template'
    _inherit = ['advanced.inventory.design.mixin']
    _description = 'Sign Design'
    _design_unit = 'px'
    _design_size_limits = (100, 7680)

    target = fields.Selection(default='aisle')
    page_width = fields.Float(string='Width (px)', default=1920.0)
    page_height = fields.Float(string='Height (px)', default=1080.0)
    layout = fields.Json(default=lambda self: default_sign_layout(self.env.context.get('default_target', 'aisle')))
    sign_ids = fields.One2many('advanced.inventory.sign', 'template_id', string='Signs')
    sign_count = fields.Integer(compute='_compute_sign_count')

    def _compute_sign_count(self):
        for template in self:
            template.sign_count = len(template.sign_ids)

    @api.onchange('target')
    def _onchange_target_layout(self):
        if not self._origin.id:
            self.layout = default_sign_layout(self.target, self.page_width, self.page_height)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('layout'):
                vals['layout'] = default_sign_layout(vals.get('target', 'aisle'), vals.get('page_width', 1920.0),
                                                     vals.get('page_height', 1080.0))
        return super().create(vals_list)

    def action_view_signs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_inventory.action_inventory_sign')
        action['domain'] = [('template_id', '=', self.id)]
        action['context'] = {'default_template_id': self.id}
        return action

    def action_open_preview(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': '/inventory/signage/design/%s' % self.id}

# -*- coding: utf-8 -*-
import hashlib
import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .design_mixin import LOCATION_TARGETS, TARGETS


class AdvancedInventorySign(models.Model):
    """A digital sign: a sign design shown for one warehouse, location or
    product, on any screen through the Inventory Signage PWA (or a Raspberry
    Pi Node with IoT Interfaces)."""
    _name = 'advanced.inventory.sign'
    _description = 'Digital Sign'
    _order = 'sequence, name, id'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True, default=lambda self: self.env.company)
    template_id = fields.Many2one(
        'advanced.inventory.sign.template', string='Sign Design', required=True, ondelete='restrict',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    target = fields.Selection(related='template_id.target', string='For')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse',
                                   domain="[('company_id', '=', company_id)]")
    location_id = fields.Many2one(
        'stock.location', string='Location',
        domain="[('storage_level', '=', target), '|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    product_id = fields.Many2one('product.product', string='Product')
    refresh_seconds = fields.Integer(
        string='Refresh Every (s)', default=60,
        help='How often the screen fetches the sign again (stock lists, names, ...). The clock ticks on its own.')
    last_seen = fields.Datetime(string='Last Shown', readonly=True, copy=False,
                                help='When a screen last fetched this sign.')
    signage_url = fields.Char(string='Screen Address', compute='_compute_signage_url',
                              help='Open on the screen (logged in to Odoo), or install it as the Inventory Signage app.')

    @api.constrains('template_id', 'warehouse_id', 'location_id', 'product_id')
    def _check_record(self):
        for sign in self:
            if not sign._sign_record():
                raise ValidationError(self.env._('Choose the %(what)s that "%(sign)s" is for.',
                                                 what=dict(TARGETS)[sign.target].lower(), sign=sign.name))

    def _compute_signage_url(self):
        base = self.get_base_url()
        for sign in self:
            sign.signage_url = '%s/inventory/signage/%s' % (base, sign.id) if sign.id else False

    @api.onchange('location_id')
    def _onchange_location_id(self):
        if self.location_id and not self.name:
            self.name = self.location_id.display_name
        if self.location_id.warehouse_id:
            self.warehouse_id = self.location_id.warehouse_id

    def _sign_record(self):
        self.ensure_one()
        if self.target == 'warehouse':
            return self.warehouse_id
        if self.target in LOCATION_TARGETS:
            return self.location_id if self.location_id.storage_level == self.target else self.env['stock.location']
        if self.target == 'product':
            return self.product_id
        return False

    def _sign_content(self):
        """The sign's page, ready to show: HTML, page size and a digest the
        screen compares to skip redrawing when nothing changed."""
        self.ensure_one()
        template = self.template_id.sudo()
        record = self._sign_record()
        rendered = template.with_company(self.company_id)._design_render(record)
        html = self.env['ir.qweb']._render('advanced_inventory.design_page', {
            'page': rendered, 'page_class': 'o_inventory_sign_page',
        })
        html = str(html)
        return {
            'name': self.name,
            'html': html,
            'width': template.page_width,
            'height': template.page_height,
            'background': template._design_color(template.background_color, self.company_id, '#FFFFFF'),
            'refresh': max(self.refresh_seconds, 10),
            'digest': hashlib.sha256(json.dumps([html, template.page_width, template.page_height]).encode()).hexdigest(),
        }

    def _sign_seen(self):
        """Remember a screen fetched the sign (at most once a minute)."""
        now = fields.Datetime.now()
        for sign in self.sudo():
            if not sign.last_seen or (now - sign.last_seen).total_seconds() > 60:
                sign.last_seen = now

    def action_open_sign(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'target': 'new', 'url': '/inventory/signage/%s' % self.id}

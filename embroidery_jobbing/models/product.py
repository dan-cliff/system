# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

HEX_COLOUR = re.compile(r'#[0-9a-f]{6}')


def normalise_hex(value):
    """'#AbC', 'aabbcc' or ' #AABBCC ' -> '#aabbcc'; other values unchanged."""
    if not value:
        return value
    text = value.strip().lower()
    if not text.startswith('#'):
        text = '#' + text
    if re.fullmatch(r'#[0-9a-f]{3}', text):
        text = '#' + ''.join(c * 2 for c in text[1:])
    return text


class EmbroideryThreadType(models.Model):
    """What a thread is made of or used for (Polyester 40wt, Rayon, Metallic, ...)."""
    _name = 'embroidery.thread.type'
    _description = 'Thread Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()
    product_count = fields.Integer(compute='_compute_product_count', string='Threads')

    def _compute_product_count(self):
        counts = dict(self.env['product.template']._read_group(
            [('thread_type_id', 'in', self.ids)], ['thread_type_id'], ['__count'],
        ))
        for thread_type in self:
            thread_type.product_count = counts.get(thread_type, 0)


class ProductCategory(models.Model):
    _inherit = 'product.category'

    is_thread = fields.Boolean(
        string='Includes Threads',
        help='Products in this category are embroidery threads: their form shows the thread '
             'manufacturer, name, colour and type under Advanced Details, and digitised designs '
             'pick their thread colours from them.',
    )


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_thread = fields.Boolean(related='categ_id.is_thread', string='Is a Thread', store=True)
    show_advanced_details = fields.Boolean(compute='_compute_show_advanced_details')

    thread_manufacturer_id = fields.Many2one(
        'res.partner', string='Thread Manufacturer', domain=[('is_company', '=', True)],
        help='The company that makes this thread (e.g. Madeira, Isacord, Brother).',
    )
    thread_name = fields.Char(string='Thread Name', help="The maker's name or number for the colour.")
    thread_color = fields.Char(
        string='Thread Colour', size=7,
        help='The colour as a hex code (e.g. #ff5a6e). Digitised designs match their colours to it.',
    )
    thread_type_id = fields.Many2one('embroidery.thread.type', string='Thread Type')

    @api.depends('is_thread')
    def _compute_show_advanced_details(self):
        """The Advanced Details tab shows when any of its sections does. A
        module adding a section extends this: ``super()``, then set the flag
        for the records its own section shows on (and add to the depends)."""
        for product in self:
            product.show_advanced_details = product.is_thread

    @api.constrains('thread_color')
    def _check_thread_color(self):
        for product in self:
            if product.thread_color and not HEX_COLOUR.fullmatch(product.thread_color):
                raise ValidationError(_(
                    '"%s" is not a hex colour code. Enter it as # and six digits or letters A-F, '
                    'e.g. #FF5A6E.', product.thread_color))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('thread_color'):
                vals['thread_color'] = normalise_hex(vals['thread_color'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('thread_color'):
            vals = dict(vals, thread_color=normalise_hex(vals['thread_color']))
        return super().write(vals)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _embroidery_thread_catalogue(self, manufacturer=None, thread_type=None, company=None):
        """The thread products digitised designs choose from: products in a
        category that includes threads, with a valid Thread Colour."""
        domain = [('is_thread', '=', True), ('thread_color', '!=', False)]
        if manufacturer:
            domain.append(('thread_manufacturer_id', 'child_of', manufacturer.ids))
        if thread_type:
            domain.append(('thread_type_id', 'in', thread_type.ids))
        if company:
            domain.append(('company_id', 'in', [False, company.id]))
        products = self.search(domain)
        return products.filtered(lambda p: HEX_COLOUR.fullmatch(p.thread_color or ''))

    def _embroidery_thread_info(self):
        """The thread as the digitiser and the .pes writer take it."""
        self.ensure_one()
        return {
            'product_id': self.id,
            'name': self.thread_name or self.name,
            'hex': self.thread_color,
            'catalog': self.default_code or '',
            'brand': self.thread_manufacturer_id.name or '',
        }

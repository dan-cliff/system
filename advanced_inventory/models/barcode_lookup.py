# -*- coding: utf-8 -*-
"""Barcode Database: fill in products from barcodelookup.com.

Odoo's own "Stock Barcode Database" setting installs an Odoo Enterprise module,
so on Community it can't be switched on. This is Inventory's own version: an API
key in Inventory settings, then a product's name, description, picture, weight
and category come from its barcode - on the product form and in the Scanner app.
Without a key it stays hidden and Inventory works as normal.
"""
import base64
import logging
import re

import requests

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)

API_URL = 'https://api.barcodelookup.com/v3/products'
KEY_PARAM = 'advanced_inventory.barcodelookup_api_key'
TIMEOUT = 10
MAX_IMAGE_BYTES = 5 * 1024 * 1024
WEIGHT_UNITS = {'kg': 1.0, 'g': 0.001, 'lb': 0.45359237, 'lbs': 0.45359237, 'oz': 0.028349523125}


class BarcodeLookupError(Exception):
    """The Barcode Database couldn't be asked (no key, bad key, network...)."""


class AdvancedInventoryBarcodeLookup(models.AbstractModel):
    _name = 'advanced.inventory.barcode.lookup'
    _description = 'Barcode Database'

    @api.model
    def _api_key(self):
        return (self.env['ir.config_parameter'].sudo().get_param(KEY_PARAM) or '').strip()

    @api.model
    def _available(self):
        return bool(self._api_key())

    @api.model
    def _no_key_message(self):
        return self.env._(
            'The Barcode Database is off: add a barcodelookup.com API key in Inventory › Configuration › '
            'Settings › Barcode Database.')

    @api.model
    def _fetch(self, barcode):
        """The Barcode Database's details for a barcode, or None when it doesn't know it.

        Raises BarcodeLookupError when it can't be asked."""
        barcode = (barcode or '').strip()
        key = self._api_key()
        if not key:
            raise BarcodeLookupError(self._no_key_message())
        if not barcode:
            return None
        try:
            response = requests.get(API_URL, params={'barcode': barcode, 'formatted': 'y', 'key': key},
                                    timeout=TIMEOUT)
        except requests.RequestException as error:
            _logger.warning('Barcode Database: could not reach barcodelookup.com: %s', error)
            raise BarcodeLookupError(self.env._(
                "Couldn't reach the Barcode Database (barcodelookup.com). Please try again in a moment."))
        if response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            raise BarcodeLookupError(self.env._(
                'The Barcode Database refused the API key. Check the key in Inventory › Configuration › '
                'Settings › Barcode Database.'))
        if response.status_code == 429:
            raise BarcodeLookupError(self.env._(
                "The Barcode Database's lookup limit for your API key has been reached. Try again later "
                "or upgrade the plan on barcodelookup.com."))
        if not response.ok:
            _logger.warning('Barcode Database: HTTP %s for %s', response.status_code, barcode)
            raise BarcodeLookupError(self.env._(
                'The Barcode Database answered with an error (%s). Please try again later.', response.status_code))
        try:
            products = (response.json() or {}).get('products') or []
        except ValueError:
            raise BarcodeLookupError(self.env._("The Barcode Database's answer couldn't be read."))
        return self._normalise(products[0]) if products else None

    @api.model
    def _normalise(self, product):
        def text(key):
            value = product.get(key)
            return value.strip() if isinstance(value, str) else ''
        features = [f.strip() for f in product.get('features') or [] if isinstance(f, str) and f.strip()]
        images = [url for url in product.get('images') or [] if isinstance(url, str) and url.startswith('http')]
        return {
            'barcode': text('barcode_number'),
            'name': text('title'),
            'description': text('description'),
            'features': features,
            'brand': text('brand'),
            'manufacturer': text('manufacturer'),
            'category': text('category'),
            'model': text('model') or text('mpn'),
            'weight': self._weight_kg(text('weight')),
            'images': images,
        }

    @api.model
    def _weight_kg(self, value):
        """'1.5 lbs' / '250 g' / '2kg' -> kilograms (0.0 when it can't be read)."""
        match = re.match(r'^\s*([\d.,]+)\s*([a-zA-Z]+)', value or '')
        if not match:
            return 0.0
        unit = WEIGHT_UNITS.get(match.group(2).lower())
        try:
            return round(float(match.group(1).replace(',', '')) * unit, 3) if unit else 0.0
        except ValueError:
            return 0.0

    @api.model
    def _image(self, urls):
        """The first picture that downloads, as base64 (False when none does)."""
        for url in urls[:3]:
            try:
                response = requests.get(url, timeout=TIMEOUT, stream=True)
                if not response.ok or not response.headers.get('Content-Type', '').startswith('image/'):
                    continue
                content = response.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
                if content and len(content) <= MAX_IMAGE_BYTES:
                    return base64.b64encode(content).decode()
            except (requests.RequestException, OSError, ValueError) as error:
                _logger.info('Barcode Database: picture %s could not be downloaded: %s', url, error)
        return False

    @api.model
    def _category(self, path):
        """The product category whose name is the most specific part of 'A > B > C'."""
        for name in reversed([part.strip() for part in (path or '').split('>') if part.strip()]):
            category = self.env['product.category'].search([('name', '=ilike', name)], limit=1)
            if category:
                return category
        return self.env['product.category']

    @api.model
    def _description_html(self, data):
        parts = []
        if data['description']:
            parts.append('<p>%s</p>' % html_escape(data['description']))
        if data['features']:
            parts.append('<ul>%s</ul>' % ''.join('<li>%s</li>' % html_escape(f) for f in data['features']))
        details = [(self.env._('Brand'), data['brand']), (self.env._('Manufacturer'), data['manufacturer']),
                   (self.env._('Model'), data['model'])]
        details = [(label, value) for label, value in details if value]
        if details:
            parts.append('<p>%s</p>' % '<br/>'.join(
                '<b>%s:</b> %s' % (html_escape(label), html_escape(value)) for label, value in details))
        return ''.join(parts)

    @api.model
    def _product_values(self, data, product=None, only_empty=True):
        """Product field values from the Barcode Database's details.

        ``only_empty``: leave fields the product already has alone."""
        def wanted(field):
            return not only_empty or not product or not product[field]
        vals = {}
        if data['name'] and wanted('name'):
            vals['name'] = data['name']
        description = self._description_html(data)
        if description and wanted('description'):
            vals['description'] = description
        if data['description'] and wanted('description_sale'):
            vals['description_sale'] = data['description']
        if data['weight'] and wanted('weight'):
            vals['weight'] = data['weight']
        category = self._category(data['category'])
        if category and (not only_empty or not product or not product.categ_id
                         or product.categ_id == self.env.ref('product.product_category_goods', False)):
            vals['categ_id'] = category.id
        if data['images'] and wanted('image_1920'):
            image = self._image(data['images'])
            if image:
                vals['image_1920'] = image
        return vals

    @api.model
    def lookup_or_raise(self, barcode):
        try:
            data = self._fetch(barcode)
        except BarcodeLookupError as error:
            raise UserError(str(error))
        if not data:
            raise UserError(self.env._('The Barcode Database doesn\'t know the barcode %s.', barcode))
        return data

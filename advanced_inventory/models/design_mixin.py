# -*- coding: utf-8 -*-
"""Shared engine of the label and sign designers.

A design is a page (millimetres for labels, pixels for signs) holding a list
of elements in a Json ``layout``. The same code draws an element for the
designer's canvas, the label PDF and the digital sign, so what is designed is
what prints and shows. Adapted from Personnel's ID badge designer.
"""
import base64
import re
import uuid

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import formatLang, html2plaintext
from odoo.tools.image import image_data_uri

PLACEHOLDER_RE = re.compile(r'\{\{\s*([A-Za-z_][\w.]*)\s*\}\}')
COLOR_RE = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$')
FONTS = {
    'Lato': "'Lato', 'Helvetica Neue', Arial, sans-serif",
    'Arial': 'Arial, Helvetica, sans-serif',
    'Helvetica': "'Helvetica Neue', Helvetica, Arial, sans-serif",
    'Verdana': 'Verdana, Geneva, sans-serif',
    'Georgia': 'Georgia, serif',
    'Times New Roman': "'Times New Roman', Times, serif",
    'Courier New': "'Courier New', Courier, monospace",
}
ELEMENT_TYPES = ('text', 'image', 'qr', 'barcode', 'shape', 'stock_list', 'clock')
# What a design is for. Code (which records it prints for, which fields it
# offers) depends on these, so they are a fixed selection.
TARGETS = [
    ('product', 'Product'),
    ('warehouse', 'Warehouse'),
    ('room', 'Room'),
    ('aisle', 'Aisle'),
    ('shelf', 'Shelf'),
    ('tote', 'Tote'),
]
LOCATION_TARGETS = ('room', 'aisle', 'shelf', 'tote')
DEFAULT_PRIMARY = '#5B3DB8'
DEFAULT_SECONDARY = '#14A3A3'
CODE_DPI = 300
SYMBOLOGIES = {'code128': 'Code128', 'ean13': 'EAN13', 'code39': 'Extended39'}


def target_model(target):
    if target == 'product':
        return 'product.product'
    if target == 'warehouse':
        return 'stock.warehouse'
    return 'stock.location'


class AdvancedInventoryDesignMixin(models.AbstractModel):
    _name = 'advanced.inventory.design.mixin'
    _description = 'Label and Sign Design'
    _order = 'sequence, id'
    # 'mm' (labels) or 'px' (signs)
    _design_unit = 'mm'
    _design_size_limits = (10, 450)

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', index=True,
        help='Only offered for this company\'s records. Leave empty to offer it to every company.')
    target = fields.Selection(TARGETS, string='For', required=True, default='product')
    target_model = fields.Char(compute='_compute_target_model')
    page_width = fields.Float(string='Width', required=True)
    page_height = fields.Float(string='Height', required=True)
    background_color = fields.Char(string='Background', default='#FFFFFF')
    background_image = fields.Image(string='Background Image', max_width=3840, max_height=3840)
    layout = fields.Json(string='Layout')
    preview_product_id = fields.Many2one('product.product', string='Preview Product')
    preview_warehouse_id = fields.Many2one('stock.warehouse', string='Preview Warehouse')
    preview_location_id = fields.Many2one(
        'stock.location', string='Preview Location', domain="[('storage_level', '=', target)]")
    preview_res_id = fields.Integer(compute='_compute_preview_res_id')
    element_count = fields.Integer(compute='_compute_element_count')

    @api.depends('target')
    def _compute_target_model(self):
        for design in self:
            design.target_model = target_model(design.target)

    @api.depends('target', 'preview_product_id', 'preview_warehouse_id', 'preview_location_id')
    def _compute_preview_res_id(self):
        for design in self:
            design.preview_res_id = design._design_preview_record().id or 0

    @api.depends('layout')
    def _compute_element_count(self):
        for design in self:
            design.element_count = len(design.layout or [])

    @api.constrains('page_width', 'page_height')
    def _check_page_size(self):
        low, high = self._design_size_limits
        for design in self:
            if not (low <= design.page_width <= high and low <= design.page_height <= high):
                raise ValidationError(self.env._('The page must be between %(low)s and %(high)s %(unit)s on each side.',
                                                 low=low, high=high, unit=self._design_unit))

    @api.constrains('background_color')
    def _check_background_color(self):
        for design in self:
            if design.background_color and not COLOR_RE.match(design.background_color):
                raise ValidationError(self.env._('The background colour must be a hex colour such as #FFFFFF.'))

    @api.constrains('layout')
    def _check_layout(self):
        for design in self:
            layout = design.layout or []
            if not isinstance(layout, list) or any(
                    not isinstance(el, dict) or el.get('type') not in ELEMENT_TYPES for el in layout):
                raise ValidationError(self.env._('The layout is not valid.'))

    @api.onchange('target')
    def _onchange_target_preview(self):
        self.preview_location_id = False

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for design, vals in zip(self, vals_list):
            vals.setdefault('name', self.env._('%s (copy)', design.name))
        return vals_list

    # ── Records ───────────────────────────────────────────────────────────

    def _design_preview_record(self):
        self.ensure_one()
        if self.target == 'product':
            return self.preview_product_id
        if self.target == 'warehouse':
            return self.preview_warehouse_id
        return self.preview_location_id

    def _design_sample_record(self):
        """A record to preview the design with: the chosen one or the first that fits."""
        self.ensure_one()
        record = self._design_preview_record()
        if record:
            return record
        domain = self._design_target_domain()
        return self.env[self.target_model].search(domain, limit=1)

    def _design_target_domain(self):
        self.ensure_one()
        domain = []
        if self.target in LOCATION_TARGETS:
            domain.append(('storage_level', '=', self.target))
        if self.company_id:
            domain.append(('company_id', 'in', [self.company_id.id, False]))
        return domain

    # ── Rendering ─────────────────────────────────────────────────────────

    @api.model
    def _design_company(self, record, company=None):
        record_company = record and 'company_id' in record._fields and record.company_id
        return record_company or company or self.env.company

    @api.model
    def _design_color(self, value, company, default=False):
        if value == 'company_primary':
            return company.primary_color if company.primary_color and COLOR_RE.match(company.primary_color) else DEFAULT_PRIMARY
        if value == 'company_secondary':
            return company.secondary_color if company.secondary_color and COLOR_RE.match(company.secondary_color) else DEFAULT_SECONDARY
        if value == 'transparent':
            return 'transparent'
        if isinstance(value, str) and COLOR_RE.match(value):
            return value
        return default

    @api.model
    def _design_number(self, value, default=0.0, low=-100000.0, high=100000.0):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return min(max(number, low), high)

    @api.model
    def _design_field_value(self, record, path):
        """The value of a dotted field path on the record, as text."""
        if not record:
            return False
        names = path.split('.')
        try:
            for index, name in enumerate(names):
                field = record._fields.get(name)
                if not field:
                    return ''
                record._check_field_access(field, 'read')
                value = record[name] if len(record) <= 1 else record.mapped(name)
                last = index == len(names) - 1
                if field.type in ('many2one', 'one2many', 'many2many'):
                    if last:
                        return ', '.join(n for n in value.mapped('display_name') if n)
                    record = value[:1]
                    if not record:
                        return ''
                    continue
                if not last:
                    return ''
                return self._design_format(record, field, value)
        except AccessError:
            return ''
        return ''

    @api.model
    def _design_format(self, record, field, value):
        if field.type == 'boolean':
            return self.env._('Yes') if value else self.env._('No')
        if value is False or value is None:
            return ''
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, value)
        if field.type == 'date':
            return value.strftime('%d/%m/%Y')
        if field.type == 'datetime':
            return fields.Datetime.context_timestamp(record, value).strftime('%d/%m/%Y %H:%M')
        if field.type == 'monetary':
            currency = record[field.get_currency_field(record)] if hasattr(field, 'get_currency_field') else False
            return formatLang(self.env, value, currency_obj=currency or None)
        if field.type == 'float':
            return formatLang(self.env, value)
        if field.type == 'binary':
            return ''
        if field.type == 'html':
            return html2plaintext(value).strip()
        return str(value)

    @api.model
    def _design_fill(self, text, record, model_name, labels=False):
        """Replace {{ field.path }} placeholders. Without a record (designer
        preview) the field's label stands in, in square brackets."""
        if not text:
            return ''

        def replace(match):
            path = match.group(1)
            if labels or not record:
                return '[%s]' % self._design_path_label(path, model_name)
            return self._design_field_value(record, path) or ''
        return PLACEHOLDER_RE.sub(replace, str(text))

    @api.model
    def _design_path_label(self, path, model_name):
        model = self.env[model_name]
        labels = []
        for name in path.split('.'):
            field = model._fields.get(name)
            if not field:
                labels.append(name)
                break
            labels.append(field._description_string(self.env))
            if field.relational:
                model = self.env[field.comodel_name]
            else:
                break
        return ' › '.join(labels)

    def _design_px(self, size):
        """An element size in device pixels for drawing codes."""
        if self._design_unit == 'mm':
            return max(40, int(size / 25.4 * CODE_DPI))
        return max(40, min(int(size * 2), 4000))

    @api.model
    def _design_code_image(self, kind, value, width, height, symbology='code128'):
        if not value:
            return False
        width, height = self._design_px(width), self._design_px(height)
        kwargs = {'width': width, 'height': height, 'humanreadable': 0, 'quiet': 1}
        if kind == 'qr':
            side = min(width, height)
            kwargs.update(width=side, height=side, barLevel='M')
            barcode_type = 'QR'
        else:
            barcode_type = SYMBOLOGIES.get(symbology, 'Code128')
            if barcode_type == 'EAN13' and not (value.isdigit() and len(value) in (12, 13)):
                barcode_type = 'Code128'
        try:
            png = self.env['ir.actions.report'].barcode(barcode_type, value, **kwargs)
        except (ValueError, AttributeError):
            try:
                png = self.env['ir.actions.report'].barcode('Code128', value, **kwargs) if kind != 'qr' else False
            except (ValueError, AttributeError):
                png = False
        if not png:
            return False
        return 'data:image/png;base64,%s' % base64.b64encode(png).decode()

    @api.model
    def _design_image_src(self, element, record, company):
        source = element.get('source')
        data = False
        if source == 'record_image':
            if record and 'image_512' in record._fields:
                try:
                    data = record.image_512
                except AccessError:
                    data = False
            elif not record:
                return '/advanced_inventory/static/src/img/picture_placeholder.svg'
        elif source == 'company_logo':
            data = company.logo
        elif source == 'custom':
            src = element.get('src') or ''
            return src if src.startswith('data:image/') else False
        if not data:
            return False
        return image_data_uri(data if isinstance(data, bytes) else data.encode())

    @api.model
    def _design_stock_rows(self, record, model_name, limit=8):
        """Rows of a stock list: what a location holds, or where a product is."""
        limit = int(min(max(limit, 1), 50))
        if not record:
            return [[self.env._('[Product]'), self.env._('[Qty]')]] * min(limit, 3)
        Quant = self.env['stock.quant']
        if model_name == 'product.product':
            groups = Quant._read_group(
                [('product_id', '=', record.id), ('location_id.usage', '=', 'internal'), ('quantity', '>', 0)],
                ['location_id'], ['quantity:sum'])
            groups.sort(key=lambda g: (g[0].walk_sequence, g[0].complete_name or ''))
            return [[location.display_name, formatLang(self.env, qty, digits=0) + ' ' + record.uom_id.name]
                    for location, qty in groups[:limit]]
        location = record.lot_stock_id if model_name == 'stock.warehouse' else record
        groups = Quant._read_group(
            [('location_id', 'child_of', location.id), ('quantity', '>', 0)],
            ['product_id'], ['quantity:sum'])
        groups.sort(key=lambda g: -g[1])
        return [[product.display_name, formatLang(self.env, qty, digits=0) + ' ' + product.uom_id.name]
                for product, qty in groups[:limit]]

    def _design_render_element(self, element, record, company, labels=False):
        """Everything needed to draw one element (same in the designer, PDF and signs)."""
        unit = self._design_unit
        text_unit = 'pt' if unit == 'mm' else 'px'
        model_name = target_model(self.target) if self else 'product.product'
        kind = element.get('type')
        num = self._design_number
        x, y = num(element.get('x')), num(element.get('y'))
        w, h = max(num(element.get('w'), 10), 0.5), max(num(element.get('h'), 5), 0.5)
        style = [
            'position:absolute', 'left:%.2f%s' % (x, unit), 'top:%.2f%s' % (y, unit),
            'width:%.2f%s' % (w, unit), 'height:%.2f%s' % (h, unit), 'overflow:hidden',
        ]
        rotate = num(element.get('rotate'), 0, -360, 360)
        if rotate:
            style += ['-webkit-transform:rotate(%.1fdeg)' % rotate, 'transform:rotate(%.1fdeg)' % rotate]
        opacity = num(element.get('opacity'), 1, 0, 1)
        if opacity < 1:
            style.append('opacity:%.2f' % opacity)
        radius = num(element.get('radius'), 0, 0, 5000)
        if radius:
            style.append('border-radius:%.2f%s' % (radius, unit))
        border_width = num(element.get('border_width'), 0, 0, 200)
        if border_width:
            style.append('border:%.2f%s solid %s' % (
                border_width, unit, self._design_color(element.get('border_color'), company, '#2A3F8F')))
            style.append('box-sizing:border-box')
        result = {'id': element.get('id') or uuid.uuid4().hex[:8], 'type': kind}

        def text_style(default_size):
            return [
                'font-family:%s' % FONTS.get(element.get('font'), FONTS['Lato']),
                'font-size:%.2f%s' % (num(element.get('size'), default_size, 2, 2000), text_unit),
                'line-height:%.2f' % num(element.get('line_height'), 1.15, 0.5, 4),
                'color:%s' % self._design_color(element.get('color'), company, '#2A3F8F'),
                'font-weight:%s' % ('bold' if element.get('bold') else 'normal'),
                'font-style:%s' % ('italic' if element.get('italic') else 'normal'),
                'text-decoration:%s' % ('underline' if element.get('underline') else 'none'),
            ] + (['text-transform:uppercase'] if element.get('uppercase') else [])

        background = self._design_color(element.get('background'), company, False)
        if kind == 'shape':
            style.append('background-color:%s' % self._design_color(element.get('fill'), company, 'transparent'))
        elif background:
            style.append('background-color:%s' % background)

        if kind in ('text', 'clock'):
            if kind == 'text':
                text = self._design_fill(element.get('text'), record, model_name, labels=labels)
            else:
                now = fields.Datetime.context_timestamp(self.with_context(tz=self._design_tz(company)), fields.Datetime.now())
                fmt = {'date': '%d/%m/%Y', 'datetime': '%d/%m/%Y %H:%M'}.get(element.get('format'), '%H:%M')
                text = now.strftime(fmt)
                result['clock_format'] = element.get('format') or 'time'
            cell = [
                'display:table-cell', 'width:%.2f%s' % (w, unit), 'height:%.2f%s' % (h, unit),
                'vertical-align:%s' % {'top': 'top', 'bottom': 'bottom'}.get(element.get('valign'), 'middle'),
                'text-align:%s' % {'center': 'center', 'right': 'right'}.get(element.get('align'), 'left'),
                'word-wrap:break-word',
            ] + text_style(10 if unit == 'mm' else 48)
            result.update({'text': text, 'lines': text.split('\n'), 'cell_style': ';'.join(cell)})
        elif kind == 'image':
            src = self._design_image_src(element, record, company)
            fit = 'cover' if element.get('fit') == 'cover' else 'contain'
            if src:
                style += [
                    "background-image:url('%s')" % src,
                    'background-repeat:no-repeat', 'background-position:center center',
                    '-webkit-background-size:%s' % fit, 'background-size:%s' % fit,
                ]
            result['src'] = src
        elif kind in ('qr', 'barcode'):
            if record:
                value = self._design_fill(element.get('value'), record, model_name)
            else:
                value = self._design_fill(element.get('value'), False, model_name) or 'SAMPLE'
                value = 'SAMPLE' if '[' in value else value
            src = self._design_code_image(kind, value, w, h, element.get('symbology') or 'code128')
            if src:
                style += [
                    "background-image:url('%s')" % src,
                    'background-repeat:no-repeat', 'background-position:center center',
                    '-webkit-background-size:contain', 'background-size:contain',
                ]
            result.update({'src': src, 'value': value})
        elif kind == 'stock_list':
            rows = self._design_stock_rows(record, model_name, num(element.get('rows'), 8, 1, 50))
            header = self._design_color(element.get('header_color'), company, False)
            result.update({
                'rows': rows,
                'table_style': ';'.join(['width:100%', 'border-collapse:collapse'] + text_style(
                    8 if unit == 'mm' else 32)),
                'row_style': 'border-bottom:%s solid %s' % (
                    '0.2mm' if unit == 'mm' else '2px',
                    self._design_color(element.get('line_color'), company, '#A9ABDC')),
                'header_style': 'background-color:%s;color:#FFFFFF' % header if header else '',
                'show_header': bool(element.get('show_header')),
                'qty_label': self.env._('Qty'),
                'name_label': self.env._('Location') if model_name == 'product.product' else self.env._('Product'),
            })
        result['style'] = ';'.join(style)
        return result

    @api.model
    def _design_tz(self, company):
        return self.env.context.get('tz') or self.env.user.tz or company.partner_id.tz or 'UTC'

    def _design_page_style(self, company, scale=False):
        self.ensure_one()
        unit = self._design_unit
        style = [
            'position:relative', 'overflow:hidden',
            'width:%.2f%s' % (self.page_width, unit), 'height:%.2f%s' % (self.page_height, unit),
            'background-color:%s' % self._design_color(self.background_color, company, '#FFFFFF'),
        ]
        if self.background_image:
            style += [
                "background-image:url('data:image/png;base64,%s')" % self.background_image.decode(),
                '-webkit-background-size:100%% 100%%', 'background-size:100% 100%',
            ]
        return ';'.join(style)

    def _design_render(self, record):
        """The design filled in for one record."""
        self.ensure_one()
        company = self._design_company(record, self.company_id)
        return {
            'page_style': Markup(self._design_page_style(company)),
            'elements': [
                self._design_render_element(element, record, company)
                for element in (self.layout or []) if isinstance(element, dict) and element.get('type') in ELEMENT_TYPES
            ],
        }

    # ── Designer ──────────────────────────────────────────────────────────

    @api.model
    def design_designer_preview(self, layout, target='product', res_id=False, company_id=False):
        """Resolved text, images, codes and stock lists for the designer's canvas."""
        design = self.new({'target': target if target in dict(TARGETS) else 'product'})
        if res_id:
            record = self.env[target_model(design.target)].browse(res_id).exists()
        else:
            # No preview record chosen: show the first record the design is for.
            record = self.env[target_model(design.target)].search(design._design_target_domain(), limit=1)
        record = record or False
        company = self._design_company(
            record, self.env['res.company'].browse(company_id).exists() if company_id else None)
        elements = {}
        for element in layout or []:
            if not isinstance(element, dict) or element.get('type') not in ELEMENT_TYPES:
                continue
            rendered = design._design_render_element(element, record, company, labels=not record)
            elements[rendered['id']] = {
                'text': rendered.get('text'),
                'src': rendered.get('src'),
                'rows': rendered.get('rows'),
            }
        return {
            'elements': elements,
            'colors': {
                'company_primary': self._design_color('company_primary', company),
                'company_secondary': self._design_color('company_secondary', company),
            },
            'company_name': company.name,
            'record_name': record.display_name if record else False,
        }

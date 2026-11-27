# -*- coding: utf-8 -*-
"""Import a product catalogue with one row per variant.

Columns (CSV or Excel; headings are matched without regard to case):

    Product              the product's name (rows with the same name are one product)
    Category             product category path, e.g. "Filament / PLA" (created if missing)
    Description          sales description (first row of the product)
    Sales Price          this variant's sales price
    Cost                 this variant's cost (optional)
    Attribute: <Name>    one column per attribute, e.g. "Attribute: Colour", "Attribute: Type";
                         the variant's value for it (blank when the product doesn't use it)
    Variant Reference    the variant's Internal Reference
    Barcode              the variant's barcode (optional)
    Weight (kg)          the variant's weight (optional)
    Collection           an existing collection's name (optional)

Each product gets an attribute line per attribute it uses, so its colours (and
types or sizes) are managed as variants. The variants in the file get their
reference, barcode and weight; combinations the file doesn't list are archived.
The product's Sales Price is its cheapest variant; the other variants' prices
become price extras on the attribute values (e.g. +$2 for "Filament with
spool"). Products are matched by name, so importing the file again updates them.
"""
import base64
import csv
import io
import itertools
import re
from collections import OrderedDict, defaultdict

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError

ATTRIBUTE_PREFIX = re.compile(r'^\s*attribute\s*:\s*(.+?)\s*$', re.I)
COLUMNS = {
    'product': 'product', 'name': 'product', 'product name': 'product',
    'category': 'category', 'product category': 'category',
    'description': 'description',
    'sales price': 'price', 'price': 'price',
    'cost': 'cost',
    'variant reference': 'reference', 'internal reference': 'reference', 'sku': 'reference',
    'barcode': 'barcode',
    'weight (kg)': 'weight', 'weight': 'weight',
    'collection': 'collection',
}


def _number(value):
    if value in (None, ''):
        return None
    try:
        return float(str(value).replace(',', '').replace('$', '').strip())
    except ValueError:
        return None


class AdvancedInventoryCatalogueImport(models.TransientModel):
    _name = 'advanced.inventory.catalogue.import'
    _description = 'Import Product Catalogue'

    file = fields.Binary(string='Catalogue File', required=True)
    filename = fields.Char()
    archive_missing = fields.Boolean(
        string='Archive Unlisted Combinations', default=True,
        help='Archive the variants whose combination of values is not in the file (e.g. a colour sold only on a spool).')
    state = fields.Selection([('upload', 'Upload'), ('done', 'Done')], default='upload')
    result = fields.Html(string='Result', readonly=True, sanitize=False)

    # ── Reading ───────────────────────────────────────────────────────────

    def _read_rows(self):
        """The file's rows as dicts of header -> text."""
        self.ensure_one()
        data = base64.b64decode(self.file or b'')
        name = (self.filename or '').lower()
        if name.endswith(('.xlsx', '.xlsm')) or data[:2] == b'PK':
            try:
                import openpyxl
            except ImportError:
                raise UserError(self.env._('Excel files need the openpyxl library; save the file as CSV instead.'))
            sheet = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
            table = [['' if cell is None else str(cell) for cell in row] for row in sheet.iter_rows(values_only=True)]
        else:
            try:
                text = data.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = data.decode('latin-1')
            table = list(csv.reader(io.StringIO(text)))
        table = [row for row in table if any((cell or '').strip() for cell in row)]
        if len(table) < 2:
            raise UserError(self.env._('The file has no rows to import.'))
        headers = [(h or '').strip() for h in table[0]]
        return headers, [dict(zip(headers, [(c or '').strip() for c in row])) for row in table[1:]]

    def _parse(self, headers, rows):
        """{product name: {'category', 'description', 'collection', 'variants': [...]}} and the attribute order."""
        fields_map, attributes = {}, []
        for header in headers:
            match = ATTRIBUTE_PREFIX.match(header)
            if match:
                attributes.append((header, match.group(1)))
            elif header.lower() in COLUMNS:
                fields_map[COLUMNS[header.lower()]] = header
        if 'product' not in fields_map:
            raise UserError(self.env._('The file needs a "Product" column.'))
        products = OrderedDict()
        for number, row in enumerate(rows, start=2):
            name = row.get(fields_map['product'], '')
            if not name:
                raise UserError(self.env._('Row %s has no product name.', number))
            product = products.setdefault(name, {
                'category': row.get(fields_map.get('category'), ''),
                'description': row.get(fields_map.get('description'), ''),
                'collection': row.get(fields_map.get('collection'), ''),
                'variants': [],
            })
            values = OrderedDict((attr, row.get(header, '')) for header, attr in attributes if row.get(header, ''))
            product['variants'].append({
                'row': number,
                'values': values,
                'price': _number(row.get(fields_map.get('price'))),
                'cost': _number(row.get(fields_map.get('cost'))),
                'reference': row.get(fields_map.get('reference'), ''),
                'barcode': row.get(fields_map.get('barcode'), ''),
                'weight': _number(row.get(fields_map.get('weight'))),
            })
        return products, [attr for _header, attr in attributes]

    # ── Writing ───────────────────────────────────────────────────────────

    @api.model
    def _category(self, path, cache):
        path = ' / '.join(part.strip() for part in (path or '').split('/') if part.strip())
        if not path:
            return self.env.ref('product.product_category_goods', raise_if_not_found=False) or self.env['product.category']
        if path in cache:
            return cache[path]
        Category = self.env['product.category']
        parent = Category
        for part in path.split(' / '):
            category = Category.search([('name', '=', part), ('parent_id', '=', parent.id or False)], limit=1)
            parent = category or Category.create({'name': part, 'parent_id': parent.id or False})
        cache[path] = parent
        return parent

    @api.model
    def _attribute(self, name, cache):
        if name not in cache:
            Attribute = self.env['product.attribute']
            cache[name] = Attribute.search([('name', '=ilike', name)], limit=1) or Attribute.create({
                'name': name, 'create_variant': 'always', 'display_type': 'pills'})
        return cache[name]

    @api.model
    def _value(self, attribute, name):
        Value = self.env['product.attribute.value']
        return Value.search([('attribute_id', '=', attribute.id), ('name', '=ilike', name)], limit=1) or Value.create(
            {'attribute_id': attribute.id, 'name': name})

    @api.model
    def _price_extras(self, variants, attribute_order):
        """Split the variants' prices into a base price and extras per attribute value,
        so base + the extras of a variant's values gives its price where possible.

        Each attribute order gives one split (an attribute's extras are the smallest
        price steps left after the attributes before it). The split that explains
        the most prices, then with the fewest extras, wins."""
        priced = [v for v in variants if v['price'] is not None]
        if not priced:
            return None, {}, []
        base = min(v['price'] for v in priced)

        def split(order):
            extras = defaultdict(float)
            for attribute in order:
                by_value = defaultdict(list)
                for variant in priced:
                    value = variant['values'].get(attribute)
                    if value:
                        rest = sum(extras[(a, variant['values'][a])] for a in variant['values'] if a != attribute)
                        by_value[value].append(variant['price'] - base - rest)
                for value, gaps in by_value.items():
                    extras[(attribute, value)] = round(max(min(gaps), 0.0), 2)
            mismatched = [v for v in priced if abs(
                base + sum(extras[(a, x)] for a, x in v['values'].items()) - v['price']) > 0.005]
            return dict(extras), mismatched

        best = None
        orders = itertools.permutations(attribute_order) if len(attribute_order) <= 5 else [attribute_order]
        for order in orders:
            extras, mismatched = split(order)
            score = (len(mismatched), sum(1 for x in extras.values() if x))
            if best is None or score < best[0]:
                best = (score, extras, mismatched)
        return base, best[1], best[2]

    def action_import(self):
        self.ensure_one()
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(self.env._('Only Inventory administrators can import a catalogue.'))
        headers, rows = self._read_rows()
        products, attribute_order = self._parse(headers, rows)
        Template = self.env['product.template']
        categories, attributes = {}, {}
        created = updated = variant_count = archived = 0
        warnings = []
        for name, spec in products.items():
            category = self._category(spec['category'], categories)
            template = Template.with_context(active_test=False).search([('name', '=', name)], limit=1)
            vals = {'name': name, 'type': 'consu', 'is_storable': True, 'categ_id': category.id}
            if spec['description']:
                vals['description_sale'] = spec['description']
            if spec['collection']:
                collection = self.env['advanced.inventory.collection'].search([('name', '=', spec['collection'])], limit=1)
                if collection:
                    vals['collection_id'] = collection.id
                else:
                    warnings.append(self.env._('%(product)s: there is no collection called "%(collection)s".',
                                               product=name, collection=spec['collection']))
            if template:
                template.write(vals)
                updated += 1
            else:
                template = Template.create(vals)
                created += 1

            # Attribute lines: every value the product's variants use, attribute by attribute.
            used = OrderedDict()
            for attribute in attribute_order:
                names = []
                for variant in spec['variants']:
                    value = variant['values'].get(attribute)
                    if value and value not in names:
                        names.append(value)
                if names:
                    used[attribute] = names
            commands = []
            for attribute, names in used.items():
                record = self._attribute(attribute, attributes)
                value_ids = [self._value(record, value).id for value in names]
                line = template.attribute_line_ids.filtered(lambda l: l.attribute_id == record)
                if line:
                    commands.append((1, line.id, {'value_ids': [(4, vid) for vid in value_ids]}))
                else:
                    commands.append((0, 0, {'attribute_id': record.id, 'value_ids': [(6, 0, value_ids)]}))
            if commands:
                template.write({'attribute_line_ids': commands})

            # Prices: cheapest variant as the Sales Price, the rest as price extras.
            base, extras, mismatched = self._price_extras(spec['variants'], list(used))
            if base is not None:
                template.list_price = base
            for ptav in template.attribute_line_ids.product_template_value_ids:
                extra = extras.get((ptav.attribute_id.name, ptav.name))
                if extra is None:
                    extra = next((x for (a, v), x in extras.items()
                                  if a.lower() == ptav.attribute_id.name.lower() and v.lower() == ptav.name.lower()), None)
                if extra is not None and ptav.price_extra != extra:
                    ptav.price_extra = extra
            for variant in mismatched:
                warnings.append(self.env._(
                    '%(product)s, row %(row)s: its price %(price)s can\'t be made from a base price and price extras; '
                    'check the variant\'s price after the import.', product=name, row=variant['row'], price=variant['price']))

            # Variants: match each row to its combination of values.
            listed = self.env['product.product']
            all_variants = template.with_context(active_test=False).product_variant_ids
            for variant in spec['variants']:
                wanted = {(a.lower(), v.lower()) for a, v in variant['values'].items()}
                product = all_variants.filtered(lambda p: {
                    (ptav.attribute_id.name.lower(), ptav.name.lower())
                    for ptav in p.product_template_attribute_value_ids} == wanted)[:1]
                if not product:
                    warnings.append(self.env._('%(product)s, row %(row)s: no variant has these values.',
                                               product=name, row=variant['row']))
                    continue
                product_vals = {'active': True}
                if variant['reference']:
                    product_vals['default_code'] = variant['reference']
                if variant['barcode']:
                    clash = self.env['product.product'].with_context(active_test=False).search(
                        [('barcode', '=', variant['barcode']), ('id', '!=', product.id)], limit=1)
                    if clash:
                        warnings.append(self.env._('%(product)s, row %(row)s: barcode %(barcode)s is already used by %(other)s.',
                                                   product=name, row=variant['row'], barcode=variant['barcode'],
                                                   other=clash.display_name))
                    else:
                        product_vals['barcode'] = variant['barcode']
                if variant['weight'] is not None:
                    product_vals['weight'] = variant['weight']
                if variant['cost'] is not None:
                    product_vals['standard_price'] = variant['cost']
                product.write(product_vals)
                listed |= product
                variant_count += 1
            if self.archive_missing and used:
                unlisted = all_variants - listed
                if unlisted:
                    unlisted.write({'active': False})
                    archived += len(unlisted)

        summary = self.env._(
            '%(created)s products created, %(updated)s updated, %(variants)s variants set, '
            '%(archived)s unlisted combinations archived.', created=created, updated=updated,
            variants=variant_count, archived=archived)
        body = Markup('<p><strong>%s</strong></p>') % summary
        if warnings:
            body += Markup('<p>%s</p><ul>%s</ul>') % (
                self.env._('Check these:'), Markup('').join(Markup('<li>%s</li>') % escape(w) for w in warnings[:200]))
        self.write({'state': 'done', 'result': body})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_view_products(self):
        return self.env['ir.actions.act_window']._for_xml_id('stock.product_template_action_product')

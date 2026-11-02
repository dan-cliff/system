# -*- coding: utf-8 -*-
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AdvancedInventorySeason(models.Model):
    """Seasons a collection can belong to (an option list under Configuration)."""
    _name = 'advanced.inventory.season'
    _description = 'Season'
    _order = 'sequence, name, id'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('UNIQUE(name)', 'This season already exists.')


class AdvancedInventoryCollection(models.Model):
    """A product collection (e.g. "Winter 2026 Candles"). Products in one of
    the collection's categories (or a category below them) can be put in it."""
    _name = 'advanced.inventory.collection'
    _description = 'Collection'
    _order = 'year desc, season_id, name, id'

    name = fields.Char(string='Name', required=True, translate=True)
    description = fields.Html(string='Description', translate=True)
    year = fields.Date(
        string='Year', default=lambda self: fields.Date.context_today(self).replace(month=1, day=1),
        help='The collection\'s year (stored as 1 January of that year; the picker only offers years).')
    season_id = fields.Many2one('advanced.inventory.season', string='Season', ondelete='restrict')
    category_ids = fields.Many2many(
        'product.category', 'advanced_inventory_collection_category_rel', 'collection_id', 'category_id',
        string='Product Categories',
        help='Products in these categories, or in categories below them, can be put in this collection.')
    company_id = fields.Many2one(
        'res.company', string='Company', index=True,
        help='Only offered for this company\'s products. Leave empty to share it with every company.')
    active = fields.Boolean(default=True)
    product_tmpl_ids = fields.One2many('product.template', 'collection_id', string='Products')
    product_count = fields.Integer(compute='_compute_product_count', string='Products')

    @api.model
    def _year_start(self, value):
        """1 January of the value's year (a date, a date string or a year number)."""
        if not value:
            return value
        if isinstance(value, int):
            return date(value, 1, 1)
        return fields.Date.to_date(value).replace(month=1, day=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('year'):
                vals['year'] = self._year_start(vals['year'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('year'):
            vals = dict(vals, year=self._year_start(vals['year']))
        return super().write(vals)

    @api.constrains('year')
    def _check_year(self):
        for collection in self:
            if collection.year and not 1900 <= collection.year.year <= 2999:
                raise ValidationError(self.env._('The year must be a four-digit year, such as 2026.'))

    def _compute_product_count(self):
        groups = dict(self.env['product.template']._read_group(
            [('collection_id', 'in', self.ids)], ['collection_id'], ['__count']))
        for collection in self:
            collection.product_count = groups.get(collection, 0)

    @api.depends('name', 'season_id', 'year')
    def _compute_display_name(self):
        for collection in self:
            year = str(collection.year.year) if collection.year else ''
            extra = ' '.join(part for part in (collection.season_id.name, year) if part)
            collection.display_name = '%s (%s)' % (collection.name, extra) if extra else collection.name

    @api.model
    def _for_category(self, category, company=None):
        """The collections a product in this category can belong to."""
        if not category:
            return self.browse()
        domain = [('category_ids', 'parent_of', category.id)]
        if company:
            domain += ['|', ('company_id', '=', False), ('company_id', '=', company.id)]
        return self.search(domain)

    def action_view_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.display_name,
            'res_model': 'product.template',
            'view_mode': 'list,kanban,form',
            'domain': [('collection_id', '=', self.id)],
            'context': {'default_collection_id': self.id,
                        'default_categ_id': self.category_ids[:1].id if len(self.category_ids) == 1 else False},
        }

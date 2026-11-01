# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCollections(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Category = cls.env['product.category']
        cls.homewares = Category.create({'name': 'Homewares'})
        cls.candles = Category.create({'name': 'Candles', 'parent_id': cls.homewares.id})
        cls.soap = Category.create({'name': 'Soap'})
        cls.collection = cls.env['advanced.inventory.collection'].create({
            'name': 'Midwinter Glow', 'description': '<p>Warm scents</p>', 'year': 2026,
            'season_id': cls.env.ref('advanced_inventory.season_winter').id,
            'category_ids': [(6, 0, cls.homewares.ids)]})

    def test_display_name(self):
        self.assertEqual(self.collection.display_name, 'Midwinter Glow (Winter 2026)')

    def test_year_check(self):
        with self.assertRaises(ValidationError):
            self.collection.year = 26

    def test_available_for_category_and_below(self):
        Collection = self.env['advanced.inventory.collection']
        self.assertEqual(Collection._for_category(self.homewares), self.collection)
        self.assertEqual(Collection._for_category(self.candles), self.collection, 'Child categories count')
        self.assertFalse(Collection._for_category(self.soap))
        candle = self.env['product.template'].create({'name': 'Candle', 'categ_id': self.candles.id})
        soap = self.env['product.template'].create({'name': 'Soap Bar', 'categ_id': self.soap.id})
        self.assertTrue(candle.collection_available)
        self.assertFalse(soap.collection_available)
        # The field's domain offers the collection for the candle only.
        domain = candle._fields['collection_id'].domain
        self.assertIn('parent_of', domain)
        self.assertEqual(self.env['advanced.inventory.collection'].search(
            [('category_ids', 'parent_of', candle.categ_id.id)]), self.collection)
        self.assertFalse(self.env['advanced.inventory.collection'].search(
            [('category_ids', 'parent_of', soap.categ_id.id)]))

    def test_product_form_and_category_change(self):
        with Form(self.env['product.template']) as form:
            form.name = 'Glow Candle'
            form.categ_id = self.candles
            form.collection_id = self.collection
            product = form.save()
        self.assertEqual(product.collection_id, self.collection)
        self.assertEqual(self.collection.product_count, 1)
        with Form(product) as form:
            form.categ_id = self.soap
        self.assertFalse(product.collection_id, 'Moving out of the collection\'s categories clears it')

    def test_filter_products(self):
        product = self.env['product.template'].create({
            'name': 'Glow Candle', 'categ_id': self.candles.id, 'collection_id': self.collection.id})
        self.env['product.template'].create({'name': 'Other', 'categ_id': self.candles.id})
        self.assertEqual(self.env['product.template'].search([('collection_id', '=', self.collection.id)]), product)
        self.assertEqual(self.env['product.product'].search([('collection_id', '=', self.collection.id)]),
                         product.product_variant_ids)
        groups = self.env['product.template']._read_group(
            [('categ_id', '=', self.candles.id)], ['collection_id'], ['__count'])
        self.assertIn((self.collection, 1), groups)


@tagged('post_install', '-at_install')
class TestDashboardFilters(TransactionCase):

    def test_company_and_type_filters(self):
        Overview = self.env['advanced.inventory.overview']
        data = Overview.get_overview_data()
        self.assertTrue(all(op['company'] for op in data['operations']), 'Each operation shows its company')
        self.assertEqual([c['key'] for c in data['filters']['codes']], ['incoming', 'outgoing', 'internal'])
        receipts = Overview.get_overview_data(codes=['incoming'])
        self.assertTrue(receipts['operations'])
        self.assertTrue(all(op['code'] == 'incoming' for op in receipts['operations']))
        self.assertEqual(receipts['filters']['selected_codes'], ['incoming'])

        other = self.env['res.company'].create({'name': 'Second Shop'})
        self.env.user.company_ids |= other
        both = Overview.with_context(allowed_company_ids=[self.env.company.id, other.id])
        data = both.get_overview_data()
        self.assertEqual({c['name'] for c in data['filters']['companies']}, {self.env.company.name, 'Second Shop'})
        companies = {op['company'] for op in data['operations']}
        self.assertIn('Second Shop', companies)
        only_other = both.get_overview_data(company_ids=[other.id])
        self.assertEqual({op['company'] for op in only_other['operations']}, {'Second Shop'})
        # A company not selected in the switcher can't be asked for.
        alone = Overview.with_context(allowed_company_ids=[self.env.company.id]).get_overview_data(
            company_ids=[other.id])
        self.assertNotIn('Second Shop', {op['company'] for op in alone['operations']})

# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestShopCollections(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        category = cls.env['product.category'].create({'name': 'Candles'})
        cls.collection = cls.env['advanced.inventory.collection'].create({
            'name': 'Midwinter Glow', 'year': '2026-01-01', 'season_id': cls.env.ref('advanced_inventory.season_winter').id,
            'category_ids': [(6, 0, category.ids)]})
        cls.in_collection = cls.env['product.template'].create({
            'name': 'Glow Candle', 'categ_id': category.id, 'collection_id': cls.collection.id,
            'is_published': True, 'sale_ok': True, 'list_price': 10})
        cls.other = cls.env['product.template'].create({
            'name': 'Plain Candle', 'categ_id': category.id, 'is_published': True, 'sale_ok': True, 'list_price': 8})

    def test_shop_filters_by_collection(self):
        page = self.url_open('/shop').text
        self.assertIn('o_wsale_collection_dropdown', page, 'The Collection filter is a dropdown')
        self.assertIn('Midwinter Glow', page, 'The collection is offered in the dropdown')
        self.assertIn('Winter 2026', ' '.join(page.split()), 'with its season and year')
        self.assertIn('Plain Candle', page)
        filtered = self.url_open('/shop?collection=%s' % self.collection.id).text
        self.assertIn('Glow Candle', filtered)
        self.assertNotIn('Plain Candle', filtered)
        self.assertIn('collection=%s' % self.collection.id, filtered, 'Shop links keep the collection')
        self.assertIn('Collection:', ' '.join(filtered.split()))

    def test_bad_collection_value_is_ignored(self):
        page = self.url_open('/shop?collection=abc')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Plain Candle', page.text)

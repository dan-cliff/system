# -*- coding: utf-8 -*-
from lxml import etree

from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase

CONTENT = '<h3>Beanie care</h3><p><strong>Hand wash</strong> cold, dry flat.</p><ul><li>No bleach</li><li>No tumble dry</li></ul>'


@tagged('post_install', '-at_install')
class TestTextBlocks(TransactionCase):

    def test_list_and_values(self):
        other = self.env['res.company'].create({'name': 'Other Co'})
        block = self.env['text.block'].create({
            'name': 'Wool care', 'content': CONTENT,
            'category_id': self.env.ref('product_text_blocks.category_care').id})
        self.env['text.block'].create({'name': 'Other only', 'content': '<p>x</p>', 'company_id': other.id})
        names = [b['name'] for b in self.env['text.block'].text_block_list()]
        self.assertIn('Wool care', names)
        self.assertNotIn('Other only', names, "another company's blocks are not offered")
        listed = [b for b in self.env['text.block'].text_block_list() if b['id'] == block.id][0]
        self.assertEqual(listed['category'], 'Care Instructions')
        self.assertTrue(listed['preview'].startswith('Beanie care Hand wash cold'))
        self.assertIn('<strong>', block.text_block_value())
        text = block.text_block_value(as_text=True)
        self.assertIn('Hand wash cold, dry flat.', text)
        self.assertNotIn('<', text)
        self.assertNotIn('*', text, 'no asterisks for bold or headings')
        self.assertEqual(text.splitlines()[0], 'Beanie care')
        self.assertIn('• No bleach\n• No tumble dry', text, 'list items on their own lines')

    def test_buttons_on_both_descriptions(self):
        arch = etree.fromstring(self.env['product.template'].get_views([(False, 'form')])['views']['form']['arch'])
        widgets = arch.xpath("//widget[@name='text_block_insert']")
        fields = {w.getnext().get('name') for w in widgets}
        self.assertIn('description_sale', fields)
        if 'description_ecommerce' in self.env['product.template']._fields:
            self.assertIn('description_ecommerce', fields)


@tagged('post_install', '-at_install')
class TestTextBlocksTour(HttpCase):

    def test_insert_in_the_browser(self):
        if 'description_ecommerce' not in self.env['product.template']._fields:
            self.skipTest('eCommerce is not installed')
        self.env['text.block'].create({'name': 'Tour beanie care', 'content': CONTENT})
        product = self.env['product.template'].create({'name': 'Merino Beanie', 'sale_ok': True,
                                                        'description_ecommerce': '<p>Soft and warm.</p>'})
        self.start_tour('/odoo/action-stock.product_template_action_product/%s' % product.id,
                        'product_text_blocks_insert', login='admin')
        self.assertIn('Hand wash cold, dry flat.', product.description_sale)
        self.assertNotIn('<strong>', product.description_sale)
        self.assertIn('Soft and warm', product.description_ecommerce)
        self.assertIn('<strong>Hand wash</strong>', product.description_ecommerce)

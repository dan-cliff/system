# -*- coding: utf-8 -*-
from unittest.mock import patch

from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase

ANSWER = """I searched the tariff.
{"suggestions": [
  {"hs_code": "611030", "national_code": "6110.30.00 / 11", "title": "Jerseys, pullovers... of man-made fibres",
   "confidence": "high", "reasoning": "Knitted garment of mainly synthetic fibre."},
  {"hs_code": "not a code", "national_code": "", "title": "x", "confidence": "high", "reasoning": "x"},
  {"hs_code": "6110.20", "national_code": "", "title": "Of cotton", "confidence": "unsure", "reasoning": "If cotton dominates."}
 ],
 "questions": ["Which fibre is greatest by weight?"],
 "summary": "Most likely 6110.30."}"""

PATH = 'odoo.addons.advanced_inventory_hs_code.models.product.'


@tagged('post_install', '-at_install')
class TestHsCodeHelper(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.template'].create({
            'name': 'Cosy Jumper', 'description_sale': 'Knitted jumper', 'is_storable': True})

    def test_button_hidden_without_ai_key(self):
        params = self.env['ir.config_parameter'].sudo()
        for key in ('claude_ai_settings.api_key', 'ai.anthropic_key', 'claude_ai_settings.gemini_api_key', 'ai.google_key'):
            params.set_param(key, False)
        self.product.invalidate_recordset()
        self.assertFalse(self.product.hs_code_ai_available)
        params.set_param('claude_ai_settings.api_key', 'sk-test')
        self.product.invalidate_recordset()
        self.assertTrue(self.product.hs_code_ai_available)

    def test_button_next_to_hs_code(self):
        arch = self.env['product.template'].get_views([(False, 'form')])['views']['form']['arch']
        widget = etree.fromstring(arch).xpath("//widget[@name='hs_code_ai_help']")
        self.assertTrue(widget)
        self.assertEqual(widget[0].getprevious().get('name'), 'hs_code')

    def test_info(self):
        info = self.product.hs_code_ai_info()
        self.assertEqual(info['name'], 'Cosy Jumper')
        self.assertEqual(info['description'], 'Knitted jumper')

    def test_suggestions(self):
        fake = {'text': ANSWER, 'found': {'https://example.org/tariff': 'Tariff'},
                'cited': ['https://example.org/tariff'], 'searched': True}
        with patch(PATH + 'ai_research', return_value=fake) as research:
            result = self.product.action_hs_code_ai_suggest('Knitted jumper, 70% acrylic 30% wool, adults')
        prompt = research.call_args[0][1]
        self.assertIn('70% acrylic', prompt)
        self.assertIn('Cosy Jumper', prompt)
        codes = [s['hs_code'] for s in result['suggestions']]
        self.assertEqual(codes, ['6110.30', '6110.20'], 'codes tidied, a non-code dropped')
        self.assertEqual(result['suggestions'][0]['national_code'], '6110.30.00 / 11', 'kept in its local format')
        self.assertEqual(result['suggestions'][1]['confidence'], 'low')
        self.assertEqual(result['sources'][0]['url'], 'https://example.org/tariff')
        self.assertEqual(result['questions'], ['Which fibre is greatest by weight?'])

    def test_variant_calls_template(self):
        fake = {'text': ANSWER, 'found': {}, 'cited': [], 'searched': False}
        with patch(PATH + 'ai_research', return_value=fake):
            result = self.product.product_variant_id.action_hs_code_ai_suggest('Knitted jumper of acrylic fibre')
        self.assertFalse(result['searched'])

    def test_needs_a_description(self):
        with self.assertRaises(UserError):
            self.product.action_hs_code_ai_suggest('jumper')

    def test_unreadable_answer(self):
        with patch(PATH + 'ai_research', return_value={'text': 'Sorry, no idea', 'found': {}, 'cited': [], 'searched': True}):
            with self.assertRaises(UserError):
                self.product.action_hs_code_ai_suggest('Knitted jumper of acrylic fibre')


@tagged('post_install', '-at_install')
class TestHsCodeHelperTour(HttpCase):

    def test_help_me_in_the_browser(self):
        self.env['ir.config_parameter'].sudo().set_param('claude_ai_settings.api_key', 'sk-test')
        product = self.env['product.template'].create({'name': 'Cosy Jumper', 'is_storable': True})
        fake = {'text': ANSWER, 'found': {'https://example.org/tariff': 'Tariff'},
                'cited': ['https://example.org/tariff'], 'searched': True}
        with patch(PATH + 'ai_research', return_value=fake):
            self.start_tour('/odoo/action-stock.product_template_action_product/%s' % product.id,
                            'advanced_inventory_hs_code_help', login='admin')
        self.assertEqual(product.hs_code, '6110.30')

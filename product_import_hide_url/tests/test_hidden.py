# -*- coding: utf-8 -*-
from lxml import etree

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestImageUrlHidden(TransactionCase):

    def test_field_hidden_on_product_forms(self):
        for model in ('product.template', 'product.product'):
            arch = self.env[model].get_views([(False, 'form')])['views']['form']['arch']
            nodes = etree.fromstring(arch).xpath("//field[@name='image_url']")
            self.assertTrue(nodes, model)
            self.assertTrue(all(n.get('invisible') in ('1', 'True', 'true') for n in nodes), model)

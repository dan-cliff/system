# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestProductCompanyFamily(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Company = cls.env['res.company']
        cls.group = Company.create({'name': 'Fam Group'})
        cls.crafts = Company.create({'name': 'Fam Crafts', 'parent_id': cls.group.id})
        cls.workshop = Company.create({'name': 'Fam Workshop', 'parent_id': cls.crafts.id})
        cls.sister = Company.create({'name': 'Fam Sister', 'parent_id': cls.group.id})
        cls.unrelated = Company.create({'name': 'Fam Other'})
        companies = cls.group | cls.crafts | cls.workshop | cls.sister | cls.unrelated
        for company in companies:
            if not cls.env['stock.warehouse'].search_count([('company_id', '=', company.id)]):
                cls.env['stock.warehouse'].create({'name': company.name, 'code': company.name[-4:].upper(),
                                                   'company_id': company.id})
        cls.user = new_test_user(
            cls.env, 'fam_user', groups='mrp.group_mrp_manager,base.group_multi_company',
            company_id=cls.group.id, company_ids=[Command.set(companies.ids)])
        Product = cls.env['product.product']
        cls.group_product = Product.create({'name': 'Fam Group Candle', 'company_id': cls.group.id})
        cls.crafts_product = Product.create({'name': 'Fam Crafts Candle', 'company_id': cls.crafts.id})
        cls.workshop_wax = Product.create({'name': 'Fam Workshop Wax', 'company_id': cls.workshop.id})
        cls.sister_product = Product.create({'name': 'Fam Sister Soap', 'company_id': cls.sister.id})
        cls.other_product = Product.create({'name': 'Fam Other Thing', 'company_id': cls.unrelated.id})
        cls.shared = Product.create({'name': 'Fam Shared Wick', 'company_id': False})

    def _env(self, company):
        return self.env(user=self.user, context={'allowed_company_ids': [company.id]})

    def _visible(self, company):
        return self._env(company)['product.product'].search([('name', 'like', 'Fam ')])

    def test_parent_sees_child_products(self):
        visible = self._visible(self.group)
        self.assertEqual(visible, self.group_product | self.crafts_product | self.workshop_wax
                         | self.sister_product | self.shared)
        templates = self._env(self.group)['product.template'].search([('name', 'like', 'Fam ')])
        self.assertIn(self.workshop_wax.product_tmpl_id, templates)

    def test_child_sees_parents_not_siblings(self):
        visible = self._visible(self.crafts)
        self.assertEqual(visible, self.group_product | self.crafts_product | self.workshop_wax | self.shared)
        self.assertNotIn(self.sister_product, visible)
        self.assertNotIn(self.other_product, self._visible(self.workshop))

    def test_parent_uses_child_products_in_manufacturing(self):
        env = self._env(self.group)
        bom = env['mrp.bom'].create({
            'product_tmpl_id': self.crafts_product.product_tmpl_id.id,
            'company_id': self.group.id,
            'bom_line_ids': [Command.create({'product_id': self.workshop_wax.id, 'product_qty': 1}),
                             Command.create({'product_id': self.shared.id, 'product_qty': 1})],
        })
        form = Form(env['mrp.production'])
        form.mrp_product_tmpl_id = self.crafts_product.product_tmpl_id
        self.assertEqual(form.bom_id, bom)
        production = form.save()
        production.action_confirm()
        self.assertEqual(production.company_id, self.group)
        self.assertEqual(production.move_raw_ids.product_id, self.workshop_wax | self.shared)

    def test_unrelated_products_refused(self):
        env = self._env(self.group)
        with self.assertRaises(UserError):
            env['mrp.production'].sudo().create({
                'product_id': self.other_product.id, 'company_id': self.group.id})._check_company()
        with self.assertRaises(UserError):
            env['mrp.production'].sudo().with_company(self.crafts).create({
                'product_id': self.sister_product.id, 'company_id': self.crafts.id})._check_company()

    def test_picker_domain(self):
        domain = self.env['product.product']._check_company_domain(self.group)
        found = self.env['product.product'].search(domain + [('name', 'like', 'Fam ')])
        self.assertIn(self.workshop_wax, found)
        self.assertNotIn(self.other_product, found)

from odoo.tests import Form, tagged, TransactionCase


@tagged('post_install', '-at_install')
class TestSaleOrderAccounts(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env['advanced.account'].create({'name': 'Acme Pty Ltd'})
        cls.globex = cls.env['advanced.account'].create({'name': 'Globex'})
        cls.jane = cls.env['advanced.contact'].create({'name': 'Jane Smith', 'account_id': cls.acme.id})

    def test_pick_contact_fills_account_and_customer(self):
        form = Form(self.env['sale.order'])
        form.adv_contact_id = self.jane
        self.assertEqual(form.adv_account_id, self.acme)
        self.assertEqual(form.partner_id, self.jane.partner_id)
        order = form.save()
        self.assertEqual(order.partner_id, self.jane.partner_id)

    def test_pick_account_only(self):
        form = Form(self.env['sale.order'])
        form.adv_account_id = self.acme
        self.assertEqual(form.partner_id, self.acme.partner_id)
        self.assertFalse(form.adv_contact_id)

    def test_changing_account_clears_other_contact(self):
        form = Form(self.env['sale.order'])
        form.adv_contact_id = self.jane
        form.adv_account_id = self.globex
        self.assertFalse(form.adv_contact_id)
        self.assertEqual(form.partner_id, self.globex.partner_id)

    def test_code_sets_partner(self):
        order = self.env['sale.order'].create({'partner_id': self.jane.partner_id.id})
        self.assertEqual(order.adv_contact_id, self.jane)
        self.assertEqual(order.adv_account_id, self.acme)

    def test_code_sets_contact(self):
        order = self.env['sale.order'].create({'adv_contact_id': self.jane.id})
        self.assertEqual(order.partner_id, self.jane.partner_id)
        self.assertEqual(order.adv_account_id, self.acme)

    def test_new_partner_joins(self):
        partner = self.env['res.partner'].create({'name': 'Walk-in Wendy'})
        order = self.env['sale.order'].create({'partner_id': partner.id})
        self.assertTrue(order.adv_contact_id)
        self.assertEqual(order.adv_contact_id.partner_id, partner)

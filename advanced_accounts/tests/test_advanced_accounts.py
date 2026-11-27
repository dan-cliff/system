from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged, TransactionCase


@tagged('post_install', '-at_install')
class TestAdvancedAccounts(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env['advanced.account']
        cls.Contact = cls.env['advanced.contact']
        cls.acme = cls.Account.create({'name': 'Acme Pty Ltd', 'email': 'hello@acme.test'})
        cls.jane = cls.Contact.create({'name': 'Jane Smith', 'account_id': cls.acme.id, 'email': 'jane@acme.test'})

    def test_account_and_contact_live_on_partners(self):
        self.assertTrue(self.acme.partner_id.is_company)
        self.assertEqual(self.acme.partner_id.name, 'Acme Pty Ltd')
        self.assertFalse(self.jane.partner_id.is_company)
        self.assertEqual(self.jane.partner_id.parent_id, self.acme.partner_id)
        self.jane.phone = '0400 000 000'
        self.assertEqual(self.jane.partner_id.phone, '0400 000 000')

    def test_contact_follows_its_partner_parent(self):
        other = self.Account.create({'name': 'Globex'})
        self.jane.partner_id.parent_id = other.partner_id
        self.assertEqual(self.jane.account_id, other)
        self.jane.account_id = self.acme
        self.assertEqual(self.jane.partner_id.parent_id, self.acme.partner_id)

    def test_display_names(self):
        self.assertEqual(self.jane.display_name, 'Jane Smith')
        formatted = self.jane.with_context(formatted_display_name=True).display_name
        self.assertEqual(formatted, 'Jane Smith --(Acme Pty Ltd)--')

    def test_search_by_account_name(self):
        found = self.Contact.name_search('Acme')
        self.assertIn(self.jane.id, [id_ for id_, _name in found])

    def test_adopt_partners(self):
        company = self.env['res.partner'].create({'name': 'Initech', 'is_company': True})
        person = self.env['res.partner'].create({'name': 'Peter Gibbons', 'parent_id': company.id})
        address = self.env['res.partner'].create({'name': 'Billing', 'parent_id': company.id, 'type': 'invoice'})
        employee_user = new_test_user(self.env, login='aa_internal', groups='base.group_user')
        self.Contact._adopt_partners(person | address | employee_user.partner_id)
        account = self.Account.search([('partner_id', '=', company.id)])
        self.assertTrue(account)
        contact = self.Contact.search([('partner_id', '=', person.id)])
        self.assertEqual(contact.account_id, account)
        self.assertFalse(self.Contact.search([('partner_id', '=', address.id)]), 'addresses are not Contacts')
        self.assertFalse(self.Contact.search([('partner_id', '=', employee_user.partner_id.id)]),
                         'internal users are not Contacts')

    def test_personnel_employees_are_not_contacts(self):
        employee = self.env['hr.employee'].create({'name': 'Erin Employee'})
        self.Contact._adopt_partners(employee.work_contact_id)
        self.assertFalse(self.Contact.search([('partner_id', '=', employee.work_contact_id.id)]))

    def test_portal_user_gets_contact(self):
        user = new_test_user(self.env, login='aa_portal', groups='base.group_portal')
        self.assertTrue(user.adv_contact_id)
        self.assertEqual(user.adv_contact_id.partner_id, user.partner_id)

    def test_create_user_for_contact(self):
        self.jane.action_create_user()
        user = self.jane.login_user_id
        self.assertTrue(user.share)
        self.assertEqual(user.login, 'jane@acme.test')
        self.assertEqual(user.adv_contact_id, self.jane)
        self.jane.name = 'Jane Brown'
        self.assertEqual(user.name, 'Jane Brown', 'the user shares the Contact\'s partner')

    def test_permissions(self):
        plain = new_test_user(self.env, login='aa_plain', groups='base.group_user')
        self.assertEqual(self.acme.with_user(plain).name, 'Acme Pty Ltd', 'every internal user can read Accounts')
        with self.assertRaises(AccessError):
            self.acme.with_user(plain).write({'name': 'Nope'})
        owner = new_test_user(self.env, login='aa_owner',
                              groups='base.group_user,advanced_accounts.group_advanced_account_edit_own')
        mine = self.Account.with_user(owner).create({'name': 'Mine Ltd'})
        mine.write({'phone': '123'})
        self.assertEqual(mine.partner_id.phone, '123', 'the partner is written for them')
        with self.assertRaises(AccessError):
            self.acme.with_user(owner).write({'name': 'Not mine'})
        with self.assertRaises(AccessError):
            mine.unlink()

    def test_contacts_app_hidden(self):
        menu = self.env.ref('contacts.menu_contacts', raise_if_not_found=False)
        if menu:
            self.assertNotIn(menu.id, self.env['ir.ui.menu']._visible_menu_ids())

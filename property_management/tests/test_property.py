# -*- coding: utf-8 -*-
import base64
from datetime import date, timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

# A 1×1 transparent PNG and the start of a PDF.
PNG = base64.b64encode(base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='))
PDF = base64.b64encode(b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n')


@tagged('post_install', '-at_install')
class TestProperty(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.landlord = cls.env['res.partner'].create({'name': 'Hilltop Holdings', 'is_company': True})
        cls.tenant = cls.env['res.partner'].create({'name': 'Corner Cafe', 'is_company': True})
        cls.monthly = cls.env.ref('property_management.rent_frequency_monthly')
        cls.office = cls.env['property.property'].create({
            'name': 'Head Office', 'ownership': 'leased_in', 'landlord_id': cls.landlord.id,
            'category_id': cls.env.ref('property_management.category_commercial').id,
            'year_built': '1985-06-30',
        })
        cls.shops = cls.env['property.property'].create({'name': 'High Street Shops', 'ownership': 'owned_leased_out'})

    def test_reference_and_year(self):
        self.assertTrue(self.office.reference.startswith('PROP/'))
        self.assertEqual(self.office.year_built, date(1985, 1, 1))
        self.assertIn(self.office.reference, self.office.display_name)
        with self.assertRaises(ValidationError):
            self.office.year_built = date(85, 1, 1)

    def test_lease_type_follows_ownership(self):
        lease_in = self.env['property.lease'].create({'property_id': self.office.id, 'partner_id': self.landlord.id})
        lease_out = self.env['property.lease'].create({'property_id': self.shops.id, 'partner_id': self.tenant.id})
        self.assertEqual((lease_in.lease_type, lease_out.lease_type), ('in', 'out'))
        self.assertTrue(lease_in.name.startswith('LSE/'))
        self.assertEqual(lease_in.company_id, self.office.company_id)

    def test_rent_totals_and_term(self):
        lease = self.env['property.lease'].create({
            'property_id': self.shops.id, 'partner_id': self.tenant.id, 'rent_amount': 2000,
            'frequency_id': self.monthly.id, 'date_start': date(2026, 1, 1), 'date_end': date(2028, 12, 31),
        })
        self.assertEqual(lease.annual_rent, 24000)
        self.assertEqual(lease.term_months, 36)
        self.assertEqual(self.shops.annual_rent_receivable, 0, 'Draft leases are not counted.')
        lease.action_activate()
        self.assertEqual(self.shops.annual_rent_receivable, 24000)
        self.assertEqual(self.shops.tenant_ids, self.tenant)
        self.assertEqual(self.shops.next_lease_end, date(2028, 12, 31))
        with self.assertRaises(ValidationError):
            lease.date_end = date(2025, 1, 1)

    def test_renew(self):
        lease = self.env['property.lease'].create({
            'property_id': self.office.id, 'partner_id': self.landlord.id,
            'date_start': date(2024, 7, 1), 'date_end': date(2027, 6, 30),
        })
        lease.action_activate()
        renewal = self.env['property.lease'].browse(lease.action_renew()['res_id'])
        self.assertEqual((renewal.date_start, renewal.date_end), (date(2027, 7, 1), date(2030, 6, 30)))
        self.assertEqual((renewal.state, renewal.previous_lease_id), ('draft', lease))
        self.assertEqual(lease.renewal_lease_id, renewal)
        with self.assertRaises(UserError):
            lease.action_renew()

    def test_cron_expires_and_reminds(self):
        today = fields.Date.context_today(self.env['property.lease'])
        old = self.env['property.lease'].create({
            'property_id': self.office.id, 'date_start': today - timedelta(days=400),
            'date_end': today - timedelta(days=1)})
        soon = self.env['property.lease'].create({
            'property_id': self.shops.id, 'date_start': today - timedelta(days=100),
            'date_end': today + timedelta(days=30), 'option_notice_date': today + timedelta(days=10)})
        (old | soon).action_activate()
        self.env['property.lease']._cron_lease_status_and_reminders()
        self.assertEqual(old.state, 'expired')
        self.assertEqual(soon.state, 'active')
        self.assertTrue(soon.is_expiring)
        self.assertIn(soon, self.env['property.lease'].search([('is_expiring', '=', True)]))
        self.assertEqual(len(soon.activity_ids), 2)
        self.assertIn((today + timedelta(days=30)).strftime('%d/%m/%Y'), ' '.join(soon.activity_ids.mapped('summary')))
        # Run again: no duplicates
        self.env['property.lease']._cron_lease_status_and_reminders()
        self.assertEqual(len(soon.activity_ids), 2)

    def test_contract(self):
        today = fields.Date.context_today(self.env['property.contract'])
        contract = self.env['property.contract'].create({
            'name': 'Building Insurance', 'property_id': self.office.id, 'amount': 1200,
            'frequency_id': self.env.ref('property_management.rent_frequency_annually').id,
            'date_end': today + timedelta(days=20),
        })
        contract.action_activate()
        self.assertEqual(self.office.annual_contract_cost, 1200)
        self.env['property.contract']._cron_contract_status_and_reminders()
        self.assertEqual(len(contract.activity_ids), 1)
        self.assertEqual(self.office.contract_count, 1)

    def test_photos_and_cover(self):
        wizard = self.env['property.photo.upload'].create({
            'property_id': self.office.id,
            'attachment_ids': [Command.create({'name': 'front.png', 'datas': PNG}),
                               Command.create({'name': 'notes.txt', 'datas': base64.b64encode(b'hi')})],
        })
        wizard.action_upload()
        self.assertEqual(self.office.photo_ids.mapped('name'), ['front'])
        self.assertTrue(self.office.image_1920, 'The first photo becomes the cover.')
        self.assertTrue(self.office.photo_ids.is_cover)
        with self.assertRaises(UserError):
            self.env['property.photo.upload'].create({'property_id': self.office.id}).action_upload()

    def test_floor_plans(self):
        plans = self.env['property.floor.plan'].create([
            {'property_id': self.office.id, 'name': 'Ground Floor', 'plan_file': PDF, 'plan_file_name': 'g.pdf'},
            {'property_id': self.office.id, 'name': 'Level 1', 'plan_file': PNG, 'plan_file_name': 'l1.png'},
        ])
        self.assertEqual(plans.mapped('file_kind'), ['pdf', 'image'])
        self.assertTrue(plans[0].plan_pdf)
        self.assertFalse(plans[0].plan_image)
        self.assertTrue(plans[1].plan_image)
        self.assertEqual(self.office.floor_plan_count, 2)


@tagged('post_install', '-at_install')
class TestPropertyAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.owner = new_test_user(
            cls.env, 'prop_owner', groups='property_management.group_property_property_edit_own')
        cls.viewer = new_test_user(
            cls.env, 'prop_viewer', groups='property_management.group_property_property_view_all')
        cls.lease_user = new_test_user(
            cls.env, 'prop_lease', groups='property_management.group_property_lease_edit_own')
        cls.nobody = new_test_user(cls.env, 'prop_nobody', groups='property_management.group_property_user')
        cls.others = cls.env['property.property'].create({'name': 'Warehouse', 'user_id': False})

    def test_own_only(self):
        Property = self.env['property.property'].with_user(self.owner)
        mine = Property.create({'name': 'Depot'})
        self.assertEqual(Property.search([]), mine)
        mine.name = 'Depot North'
        with self.assertRaises(AccessError):
            self.others.with_user(self.owner).name = 'Mine now'
        with self.assertRaises(AccessError):
            mine.unlink()
        # Photos follow their property
        self.env['property.photo'].with_user(self.owner).create({'property_id': mine.id, 'image_1920': PNG})
        with self.assertRaises(AccessError):
            self.env['property.photo'].with_user(self.owner).create(
                {'property_id': self.others.id, 'image_1920': PNG})

    def test_owner_uploads_photos(self):
        mine = self.env['property.property'].with_user(self.owner).create({'name': 'Shed'})
        attachment = self.env['ir.attachment'].with_user(self.owner).create(
            {'name': 'shed.png', 'datas': PNG, 'res_model': 'property.photo.upload'})
        wizard = self.env['property.photo.upload'].with_user(self.owner).create(
            {'property_id': mine.id, 'attachment_ids': [Command.set(attachment.ids)]})
        wizard.action_upload()
        self.assertEqual(mine.photo_ids.mapped('name'), ['shed'])
        self.assertFalse(attachment.exists())

    def test_view_all_cannot_edit(self):
        self.assertIn(self.others, self.env['property.property'].with_user(self.viewer).search([]))
        with self.assertRaises(AccessError):
            self.others.with_user(self.viewer).name = 'Changed'

    def test_lease_users_can_pick_properties(self):
        self.assertIn(self.others, self.env['property.property'].with_user(self.lease_user).search([]))
        lease = self.env['property.lease'].with_user(self.lease_user).create({'property_id': self.others.id})
        self.assertEqual(lease.user_id, self.lease_user)
        with self.assertRaises(AccessError):
            self.others.with_user(self.lease_user).name = 'Changed'

    def test_no_permission_no_access(self):
        self.assertFalse(self.env['property.property'].with_user(self.nobody).search([]))
        with self.assertRaises(AccessError):
            self.env['property.property'].with_user(self.nobody).create({'name': 'Sneaky'})

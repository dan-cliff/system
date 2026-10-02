from datetime import datetime

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import Form, new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBookingInvoicing(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.env.user.group_ids += cls.env['res.groups'].browse([
            cls.env.ref('boarding_kennel_manager.group_kennel_%s_%s' % (key, permission)).id
            for key in ('booking', 'resident', 'task', 'medication', 'observation', 'yard', 'diet')
            for permission in ('create', 'update', 'delete')
        ])
        cls.company.partner_id.tz = 'UTC'
        cls.kennel_categ = cls.env['product.category'].create({'name': 'Test Kennel Services'})
        cls.nights = cls._create_product(name='Boarding Night', lst_price=50.0, categ_id=cls.kennel_categ.id, taxes_id=False)
        cls.bath = cls._create_product(name='Bath', lst_price=30.0, categ_id=cls.kennel_categ.id, taxes_id=False)
        cls.walk = cls._create_product(name='Extra Walk', lst_price=10.0, categ_id=cls.kennel_categ.id, taxes_id=False)
        cls.company.write({'kennel_invoicing': True, 'kennel_product_categ_ids': [Command.set(cls.kennel_categ.ids)]})
        cls.rex = cls.env['kennel.resident'].create({'name': 'Rex', 'partner_id': cls.partner_a.id})
        cls.booking = cls.env['kennel.booking'].create({
            'partner_id': cls.partner_a.id, 'resident_ids': [Command.set(cls.rex.ids)],
            'arrival_datetime': datetime(2026, 10, 1, 9), 'departure_datetime': datetime(2026, 10, 5, 17),
            'product_line_ids': [
                Command.create({'product_id': cls.nights.id, 'quantity': 4}),
                Command.create({'product_id': cls.bath.id, 'quantity': 1}),
            ],
        })

    def _line(self, product, booking=None):
        return (booking or self.booking).with_context(active_test=False).product_line_ids.filtered(
            lambda line: line.product_id == product)

    def _product_lines(self, invoice):
        return {line.product_id.name: line.quantity for line in invoice.invoice_line_ids if line.product_id}

    def test_settings_and_product_filter(self):
        domain = self.company._kennel_product_domain()
        products = self.env['product.product'].search(domain)
        self.assertIn(self.nights, products)
        self.assertNotIn(self.product_a, products)
        self.assertEqual(self._line(self.nights).price_unit, 50.0)
        self.assertEqual(self.booking.amount_products, 230.0)
        settings = self.env['res.config.settings'].create({})
        self.assertTrue(settings.kennel_invoicing)
        self.assertEqual(settings.kennel_product_categ_ids, self.kennel_categ)

    def test_disabled(self):
        self.company.kennel_invoicing = False
        self.assertFalse(self.booking.has_products_to_invoice)
        with self.assertRaises(UserError):
            self.booking.action_create_invoice()

    def test_invoice_and_payment_status(self):
        self.assertTrue(self.booking.has_products_to_invoice)
        self.assertEqual(self.booking.payment_status, 'not_invoiced')
        self.booking.action_create_invoice()
        invoice = self.booking.invoice_ids
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.partner_id, self.partner_a)
        self.assertEqual(invoice.invoice_origin, self.booking.name)
        note = invoice.invoice_line_ids.filtered(lambda line: line.display_type == 'line_note')
        self.assertIn(self.booking.name, note.name)
        self.assertIn('01/10/2026 09:00', note.name)
        self.assertIn('05/10/2026 17:00', note.name)
        self.assertIn('Rex', note.name)
        self.assertEqual(self._product_lines(invoice), {'Boarding Night': 4, 'Bath': 1})
        self.assertEqual(invoice.amount_total, 230.0)
        self.assertEqual(self._line(self.nights).qty_invoiced, 4)
        self.assertFalse(self.booking.has_products_to_invoice)
        self.assertFalse(self.booking.show_amendment_prompt)
        self.assertEqual(self.booking.payment_status, 'draft')

        invoice.action_post()
        self.assertEqual(self.booking.payment_status, 'not_paid')
        self.assertEqual(self.booking.amount_due, 230.0)
        self._register_payment(invoice, amount=100.0)
        self.assertEqual(self.booking.payment_status, 'partial')
        self._register_payment(invoice)
        self.assertEqual(self.booking.payment_status, 'paid')
        self.assertEqual(self.booking.amount_due, 0.0)
        self.assertIn(invoice.name, self.booking.invoice_summary)

    def test_amendment_invoice(self):
        self.booking.action_create_invoice()
        # Two more nights, an extra walk, and no bath after all.
        self._line(self.nights).quantity = 6
        self.booking.product_line_ids = [Command.create({'product_id': self.walk.id, 'quantity': 2}),
                                         Command.unlink(self._line(self.bath).id)]
        bath = self._line(self.bath)
        self.assertTrue(bath.exists() and not bath.active, 'an invoiced line is archived, not deleted')
        self.assertTrue(self.booking.show_amendment_prompt)

        # No: nothing raised, and the question goes away until the next change.
        self.booking.action_decline_amendment()
        self.assertFalse(self.booking.show_amendment_prompt)
        self.assertEqual(self.booking.invoice_count, 1)
        self._line(self.walk).quantity = 3
        self.assertTrue(self.booking.show_amendment_prompt)

        # Yes: only the changes, the held ones included.
        self.booking.action_create_amendment_invoice()
        amendment = self.booking.invoice_ids.sorted('id')[-1]
        self.assertEqual(amendment.move_type, 'out_invoice')
        self.assertEqual(self._product_lines(amendment), {'Boarding Night': 2, 'Extra Walk': 3, 'Bath': -1})
        self.assertEqual(amendment.amount_total, 2 * 50 + 3 * 10 - 30)
        self.assertIn('Amendment', amendment.invoice_line_ids.filtered(lambda l: l.display_type == 'line_note').name)
        self.assertFalse(self.booking.show_amendment_prompt)
        self.assertFalse(self.booking._pending_product_lines())
        amendment.action_post()  # a positive total, so it posts as an invoice

    def test_removals_only_make_a_credit_note(self):
        self.booking.action_create_invoice()
        self.booking.invoice_ids.action_post()
        self._line(self.nights).quantity = 2
        self.booking.action_create_amendment_invoice()
        credit = self.booking.invoice_ids.sorted('id')[-1]
        self.assertEqual(credit.move_type, 'out_refund')
        self.assertEqual(self._product_lines(credit), {'Boarding Night': 2})
        self.assertEqual(credit.amount_total, 100.0)
        self.assertEqual(self._line(self.nights).qty_invoiced, 2)
        credit.action_post()
        self.assertEqual(self.booking.amount_invoiced, 130.0)

    def test_cancelled_invoice_puts_products_back(self):
        self.booking.action_create_invoice()
        self.booking.invoice_ids.button_cancel()
        self.assertEqual(self._line(self.nights).qty_invoiced, 0)
        self.assertTrue(self.booking.has_products_to_invoice)

    def test_uninvoiced_line_is_simply_deleted(self):
        line = self._line(self.bath)
        self.booking.product_line_ids = [Command.unlink(line.id)]
        self.assertFalse(line.exists())

    def test_keeper_raises_invoice_without_accounting_access(self):
        keeper = new_test_user(self.env, login='invoice_keeper', groups='base.group_user,boarding_kennel_manager.group_kennel_booking_create,boarding_kennel_manager.group_kennel_booking_update,boarding_kennel_manager.group_kennel_resident_create,boarding_kennel_manager.group_kennel_resident_update,boarding_kennel_manager.group_kennel_task_create,boarding_kennel_manager.group_kennel_task_update,boarding_kennel_manager.group_kennel_medication_create,boarding_kennel_manager.group_kennel_medication_update,boarding_kennel_manager.group_kennel_medication_delete,boarding_kennel_manager.group_kennel_observation_create,boarding_kennel_manager.group_kennel_observation_update,boarding_kennel_manager.group_kennel_yard_view',
                               company_id=self.company.id, company_ids=[Command.set(self.company.ids)])
        booking = self.booking.with_user(keeper)
        action = booking.action_create_invoice()
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(booking.invoice_count, 1)
        self.assertEqual(booking.payment_status, 'draft')
        self.assertIn('Draft', booking.invoice_summary)
        with Form(booking) as form:
            with form.product_line_ids.new() as line:
                line.product_id = self.walk
        self.assertTrue(booking.show_amendment_prompt)
        booking.action_create_amendment_invoice()
        self.assertEqual(booking.invoice_count, 2)

from datetime import date, datetime

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import Form, TransactionCase, tagged

DAY = date(2026, 10, 2)


@tagged('post_install', '-at_install')
class TestFeedItems(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.partner_id.tz = 'UTC'
        ref = lambda xmlid: cls.env.ref(f'boarding_kennel_manager.{xmlid}')
        cls.twice_daily = ref('kennel_frequency_twice_daily')  # 08:00, 17:00
        cls.once_daily = ref('kennel_frequency_once_daily')    # 08:00
        cls.kg = cls.env.ref('uom.product_uom_kgm')
        cls.food_categ = cls.env['product.category'].create({'name': 'Test Pet Food'})
        cls.biscuits = cls.env['product.product'].create({
            'name': 'Dry Biscuits', 'is_storable': True, 'categ_id': cls.food_categ.id, 'uom_id': cls.kg.id})
        cls.chicken = cls.env['product.product'].create({
            'name': 'Chicken Mince', 'is_storable': True, 'categ_id': cls.food_categ.id, 'uom_id': cls.kg.id})
        cls.other = cls.env['product.product'].create({'name': 'Garden Hose', 'is_storable': True})
        cls.company.write({'kennel_invoicing': True, 'kennel_product_categ_ids': [Command.set(cls.food_categ.ids)]})
        cls.diet = cls.env['kennel.diet'].create({
            'name': 'Mixed', 'food': 'ignored when food comes from inventory',
            'feed_item_ids': [
                Command.create({'product_id': cls.biscuits.id, 'quantity': 0.25, 'frequency_id': cls.twice_daily.id}),
                Command.create({'product_id': cls.chicken.id, 'quantity': 0.1, 'frequency_id': cls.once_daily.id}),
            ],
        })
        cls.customer = cls.env['res.partner'].create({'name': 'Food Customer'})
        cls.rex = cls.env['kennel.resident'].create({
            'name': 'Rex', 'partner_id': cls.customer.id, 'default_diet_id': cls.diet.id})

    def _booking(self):
        booking = self.env['kennel.booking'].create({
            'partner_id': self.customer.id, 'resident_ids': [Command.set(self.rex.ids)],
            'arrival_datetime': datetime(2026, 10, 1, 9), 'departure_datetime': datetime(2026, 10, 5, 17),
        })
        booking.write({'state': 'checked_in', 'checked_in_datetime': datetime(2026, 10, 1, 9)})
        return booking

    def test_food_offered_from_inventory(self):
        food = self.env['product.product'].search(self.company._kennel_food_domain())
        self.assertIn(self.biscuits, food)
        self.assertNotIn(self.other, food)
        # With warehouses set, only food stocked there.
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1)
        self.company.kennel_warehouse_ids = warehouse
        self.env['stock.quant']._update_available_quantity(self.biscuits, warehouse.lot_stock_id, 10)
        food = self.env['product.product'].search(self.company._kennel_food_domain())
        self.assertIn(self.biscuits, food)
        self.assertNotIn(self.chicken, food)

    def test_stay_takes_the_diets_food_items(self):
        line = self._booking().line_ids
        self.assertTrue(line.use_feed_items)
        self.assertEqual(line.feed_item_ids.product_id, self.biscuits | self.chicken)
        self.assertEqual(line.feed_item_ids.diet_id, self.env['kennel.diet'], 'copies, not the diet\'s own items')
        self.assertIn('Dry Biscuits 0.25 kg (Twice a Day)', line.feed_summary)
        self.assertIn('Chicken Mince 0.1 kg', line._feed_description())
        # Changing the stay leaves the diet alone.
        line.feed_item_ids[0].quantity = 0.5
        self.assertEqual(self.diet.feed_item_ids[0].quantity, 0.25)
        with self.assertRaises(ValidationError):
            line.feed_item_ids[0].quantity = 0

    def test_feeds_follow_each_items_frequency(self):
        booking = self._booking()
        feeds = self.env['kennel.task']._generate_for_bookings(booking, day=DAY).filtered(
            lambda task: task.task_type == 'feed').sorted('scheduled_datetime')
        self.assertEqual([task.scheduled_datetime.strftime('%H:%M') for task in feeds], ['08:00', '17:00'])
        morning, evening = feeds
        self.assertIn('Dry Biscuits', morning.instructions)
        self.assertIn('Chicken Mince', morning.instructions)
        self.assertIn('Dry Biscuits 0.25 kg', morning.quantity_given)
        self.assertIn('Dry Biscuits', evening.instructions)
        self.assertNotIn('Chicken Mince', evening.instructions)
        # A new item with its own times swaps the open feeds for the new schedule.
        three = self.env.ref('boarding_kennel_manager.kennel_frequency_three_daily')  # 07:00, 12:00, 17:00
        booking.line_ids.feed_item_ids = [Command.create({'product_id': self.chicken.id, 'quantity': 0.05,
                                                          'frequency_id': three.id})]
        self.env['kennel.task']._generate_for_bookings(booking, day=DAY)
        times = sorted(task.scheduled_datetime.strftime('%H:%M') for task in booking.task_ids
                       if task.task_type == 'feed' and task.state == 'todo' and task.date == DAY)
        self.assertEqual(times, ['07:00', '08:00', '12:00', '17:00'])

    def test_custom_diet_keeps_the_food_items(self):
        line = self._booking().line_ids
        line.feed_item_ids[1].unlink()
        action = line.action_custom_diet()
        Form(self.env[action['res_model']].with_context(action['context'])).save().action_create()
        self.assertNotEqual(line.diet_id, self.diet)
        self.assertEqual(line.diet_id.feed_item_ids.product_id, self.biscuits)
        self.assertEqual(line.feed_item_ids.product_id, self.biscuits)

    def test_text_food_when_invoicing_is_off(self):
        self.company.kennel_invoicing = False
        line = self._booking().line_ids
        self.assertFalse(line.use_feed_items)
        self.assertFalse(line.feed_item_ids)
        self.assertEqual(line._feed_description(), 'ignored when food comes from inventory')

from datetime import date, datetime

from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Command
from odoo.tests import Form, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestBoardingKennel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.kennel_invoicing = False  # food is typed in, not picked from inventory
        cls.dog = cls.env.ref('boarding_kennel_manager.kennel_species_dog')
        cls.cat = cls.env.ref('boarding_kennel_manager.kennel_species_cat')
        cls.twice_daily = cls.env.ref('boarding_kennel_manager.kennel_frequency_twice_daily')
        cls.smith = cls.env['res.partner'].create({'name': 'Test Smith'})
        cls.jones = cls.env['res.partner'].create({'name': 'Test Jones'})
        cls.dry_food = cls.env['kennel.diet'].create({
            'name': 'Adult Dog - Dry', 'species_id': cls.dog.id,
            'food': '1 cup Dry biscuits', 'frequency_id': cls.twice_daily.id,
            'instructions': 'Soak in warm water.',
        })
        cls.rex = cls.env['kennel.resident'].create({
            'name': 'Rex', 'partner_id': cls.smith.id, 'species_id': cls.dog.id,
            'default_diet_id': cls.dry_food.id, 'medical_notes': 'Allergic to chicken.',
            'vaccination_expiry_date': date(2030, 1, 1),
        })
        cls.bella = cls.env['kennel.resident'].create({
            'name': 'Bella', 'partner_id': cls.smith.id, 'species_id': cls.dog.id,
            'vaccination_expiry_date': date(2030, 1, 1),
        })
        cls.tom = cls.env['kennel.resident'].create({'name': 'Tom', 'partner_id': cls.jones.id, 'species_id': cls.cat.id})
        cls.run1 = cls.env['kennel.yard'].create({'name': 'Run 1', 'code': 'R1', 'capacity': 2, 'species_ids': [Command.set(cls.dog.ids)]})
        cls.keeper = new_test_user(cls.env, login='kennel_keeper', groups='boarding_kennel_manager.group_kennel_keeper')

    def _book(self, partner, residents, arrival=datetime(2026, 10, 1, 9), departure=datetime(2026, 10, 5, 17), **vals):
        return self.env['kennel.booking'].create({
            'partner_id': partner.id,
            'resident_ids': [Command.set(residents.ids)],
            'arrival_datetime': arrival,
            'departure_datetime': departure,
            **vals,
        })

    def test_reference_and_nights(self):
        booking = self._book(self.smith, self.rex)
        self.assertTrue(booking.name.startswith('BK'))
        self.assertEqual(booking.nights, 4)

    def test_animals_offered_are_the_customers(self):
        booking = self._book(self.smith, self.rex)
        self.assertEqual(booking._fields['resident_ids'].domain, "[('partner_id', '=', partner_id)]")
        # The same filter, evaluated for this booking.
        offered = self.env['kennel.resident'].search([('partner_id', '=', booking.partner_id.id)])
        self.assertEqual(offered, self.rex | self.bella)
        with self.assertRaises(ValidationError):
            self._book(self.smith, self.rex | self.tom)

    def test_form_changing_customer_drops_other_animals(self):
        form = Form(self.env['kennel.booking'])
        form.partner_id = self.smith
        form.arrival_datetime = datetime(2026, 10, 1, 9)
        form.departure_datetime = datetime(2026, 10, 3, 9)
        form.resident_ids.add(self.rex)
        form.resident_ids.add(self.bella)
        self.assertEqual(len(form.line_ids), 2)
        form.partner_id = self.jones
        self.assertEqual(len(form.resident_ids), 0)
        self.assertEqual(len(form.line_ids), 0)
        form.resident_ids.add(self.tom)
        booking = form.save()
        self.assertEqual(booking.line_ids.resident_id, self.tom)

    def test_lines_follow_animals_and_prefill_diet(self):
        booking = self._book(self.smith, self.rex | self.bella)
        self.assertEqual(booking.line_ids.resident_id, self.rex | self.bella)
        rex_line = booking.line_ids.filtered(lambda line: line.resident_id == self.rex)
        self.assertEqual(rex_line.diet_id, self.dry_food)
        self.assertEqual(rex_line.food, '1 cup Dry biscuits')
        self.assertFalse(rex_line.use_feed_items)
        self.assertEqual(rex_line.frequency_id, self.twice_daily)
        self.assertEqual(rex_line.feeding_instructions, 'Soak in warm water.')
        self.assertEqual(rex_line.medical_notes, 'Allergic to chicken.')

        # Taking an animal off the booking drops its line, and deleting a line takes the animal off.
        booking.resident_ids = [Command.unlink(self.bella.id)]
        self.assertEqual(booking.line_ids.resident_id, self.rex)
        booking.resident_ids = [Command.link(self.bella.id)]
        booking.line_ids = [Command.unlink(rex_line.id)]
        self.assertEqual(booking.resident_ids, self.bella)

    def test_changing_a_diet_keeps_existing_stays(self):
        booking = self._book(self.smith, self.rex)
        self.dry_food.food = '2 cups Dry biscuits'
        self.assertEqual(booking.line_ids.food, '1 cup Dry biscuits')
        # Feed details can be adjusted for the stay without touching the diet.
        booking.line_ids.food = 'Owner\'s food'
        self.assertEqual(self.dry_food.food, '2 cups Dry biscuits')

    def test_custom_diet(self):
        booking = self._book(self.smith, self.rex)
        line = booking.line_ids
        action = line.action_custom_diet()
        wizard_form = Form(self.env[action['res_model']].with_context(action['context']))
        self.assertEqual(wizard_form.food, '1 cup Dry biscuits')
        wizard_form.food = 'Raw mince'
        wizard_form.owner_supplied_food = True
        wizard_form.save().action_create()
        diet = line.diet_id
        self.assertNotEqual(diet, self.dry_food)
        self.assertEqual(diet.resident_id, self.rex)
        self.assertEqual(line.food, 'Raw mince')
        self.assertTrue(line.owner_supplied_food)
        self.assertEqual(self.rex.default_diet_id, diet)
        # Offered to Rex only.
        diets_for = lambda resident: self.env['kennel.diet'].search(
            [('resident_id', 'in', [False, resident.id]), ('species_id', 'in', [False, resident.species_id.id])])
        self.assertIn(diet, diets_for(self.rex))
        self.assertNotIn(diet, diets_for(self.bella))

    def test_dates_and_double_booking(self):
        with self.assertRaises(ValidationError):
            self._book(self.smith, self.rex, arrival=datetime(2026, 10, 5), departure=datetime(2026, 10, 1))
        first = self._book(self.smith, self.rex)
        with self.assertRaises(ValidationError):
            self._book(self.smith, self.rex, arrival=datetime(2026, 10, 4), departure=datetime(2026, 10, 8))
        # Back-to-back is fine, and a cancelled booking frees the animal.
        self._book(self.smith, self.rex, arrival=datetime(2026, 10, 5, 17), departure=datetime(2026, 10, 8))
        first.action_cancel()
        self._book(self.smith, self.rex, arrival=datetime(2026, 10, 2), departure=datetime(2026, 10, 3))

    def test_yard_capacity_and_species(self):
        rover = self.env['kennel.resident'].create({'name': 'Rover', 'partner_id': self.jones.id, 'species_id': self.dog.id})
        first = self._book(self.smith, self.rex | self.bella)
        first.line_ids.yard_id = self.run1
        second = self._book(self.jones, rover, arrival=datetime(2026, 10, 3), departure=datetime(2026, 10, 9))
        with self.assertRaises(ValidationError):
            second.line_ids.yard_id = self.run1
        # Once the first stay ends there's room.
        later = self._book(self.jones, rover, arrival=datetime(2026, 10, 10), departure=datetime(2026, 10, 12))
        later.line_ids.yard_id = self.run1
        # Two stays that each overlap this one but not each other leave room for it.
        rex_early = self._book(self.smith, self.rex, arrival=datetime(2026, 11, 1), departure=datetime(2026, 11, 3))
        bella_late = self._book(self.smith, self.bella, arrival=datetime(2026, 11, 4), departure=datetime(2026, 11, 6))
        (rex_early | bella_late).line_ids.yard_id = self.run1
        rover_long = self._book(self.jones, rover, arrival=datetime(2026, 11, 2), departure=datetime(2026, 11, 5))
        rover_long.line_ids.yard_id = self.run1
        # A dogs-only yard can't take a cat.
        cat_booking = self._book(self.jones, self.tom)
        with self.assertRaises(ValidationError):
            cat_booking.line_ids.yard_id = self.run1

    def test_vaccination_warning(self):
        booking = self._book(self.smith, self.rex | self.bella)
        self.assertFalse(booking.vaccination_warning)
        self.bella.vaccination_expiry_date = date(2026, 10, 3)
        booking.invalidate_recordset(['vaccination_warning'])
        self.assertIn('Bella', booking.vaccination_warning)
        self.assertNotIn('Rex', booking.vaccination_warning)

    def test_medication_and_log(self):
        booking = self._book(self.smith, self.rex, medication_ids=[Command.create({
            'resident_id': self.rex.id, 'name': 'Apoquel', 'dose': '1 tablet',
        })])
        medication = booking.medication_ids
        with self.assertRaises(ValidationError):
            booking.medication_ids = [Command.create({'resident_id': self.tom.id, 'name': 'Other'})]

        action = medication.action_record_dose()
        dose_form = Form(self.env[action['res_model']].with_context(action['context']))
        self.assertEqual(dose_form.dose_given, '1 tablet')
        given = dose_form.save()
        self.assertEqual(given.resident_id, self.rex)
        self.assertEqual(given.outcome_id, self.env.ref('boarding_kennel_manager.kennel_dose_outcome_given'))
        self.assertEqual(booking.administration_ids, given)
        self.assertEqual(medication.last_given_datetime, given.administered_datetime)

        refused = self.env['kennel.medication.administration'].create({
            'booking_id': booking.id, 'medication_id': medication.id,
            'administered_datetime': datetime(2030, 1, 1),
            'outcome_id': self.env.ref('boarding_kennel_manager.kennel_dose_outcome_refused').id,
        })
        self.assertTrue(refused.problem)
        self.assertEqual(medication.last_given_datetime, given.administered_datetime)

        other = self._book(self.smith, self.bella)
        with self.assertRaises(ValidationError):
            self.env['kennel.medication.administration'].create({'booking_id': other.id, 'medication_id': medication.id})

    def test_observations(self):
        booking = self._book(self.smith, self.rex)
        concern = self.env['kennel.observation'].create({
            'booking_id': booking.id, 'resident_id': self.rex.id, 'summary': 'Limping',
            'type_id': self.env.ref('boarding_kennel_manager.kennel_observation_type_health_concern').id,
        })
        general = self.env['kennel.observation'].create({
            'booking_id': booking.id, 'resident_id': self.rex.id, 'summary': 'Ate all breakfast',
        })
        self.assertTrue(concern.concern)
        self.assertFalse(general.concern)
        self.assertEqual(booking.observation_count, 2)
        self.assertEqual(booking.concern_count, 1)
        with self.assertRaises(ValidationError):
            self.env['kennel.observation'].create({'booking_id': booking.id, 'resident_id': self.tom.id, 'summary': 'x'})

    def test_workflow(self):
        booking = self._book(self.smith, self.env['kennel.resident'])
        with self.assertRaises(Exception):
            booking.action_confirm()
        booking.resident_ids = self.rex
        booking.action_confirm()
        booking.action_check_in()
        self.assertEqual(booking.state, 'checked_in')
        self.assertTrue(booking.checked_in_datetime)
        booking.line_ids.yard_id = self.run1
        self.assertEqual(self.run1.occupant_count, 1)
        booking.action_check_out()
        self.assertEqual(booking.state, 'checked_out')
        self.run1.invalidate_recordset(['occupant_count'])
        self.assertEqual(self.run1.occupant_count, 0)

    def test_partner_residents(self):
        self.assertEqual(self.smith.kennel_resident_count, 2)
        self.assertEqual(self.smith.action_view_kennel_residents()['domain'], [('partner_id', '=', self.smith.id)])

    def test_keeper_access(self):
        env = self.env(user=self.keeper)
        booking = env['kennel.booking'].create({
            'partner_id': self.smith.id, 'resident_ids': [Command.set(self.rex.ids)],
            'arrival_datetime': datetime(2026, 12, 1), 'departure_datetime': datetime(2026, 12, 2),
        })
        env['kennel.custom.diet.wizard'].create({'line_id': booking.line_ids.id}).action_create()
        self.assertEqual(booking.line_ids.diet_id.resident_id, self.rex)
        with self.assertRaises(AccessError), mute_logger('odoo.models'):
            booking.unlink()
        with self.assertRaises(AccessError), mute_logger('odoo.models'):
            env['kennel.yard'].create({'name': 'Keeper Yard'})

    def test_multi_company(self):
        company_b = self.env['res.company'].create({'name': 'Test Kennels B'})
        user_b = new_test_user(
            self.env, login='kennel_b', groups='boarding_kennel_manager.group_kennel_manager',
            company_id=company_b.id, company_ids=[Command.set(company_b.ids)],
        )
        booking = self._book(self.smith, self.rex)
        env_b = self.env(user=user_b)
        self.assertFalse(env_b['kennel.resident'].search([('id', '=', self.rex.id)]))
        self.assertFalse(env_b['kennel.booking'].search([('id', '=', booking.id)]))
        self.assertFalse(env_b['kennel.yard'].search([('id', '=', self.run1.id)]))
        # Shared (company-less) options are visible everywhere.
        self.assertTrue(env_b['kennel.species'].search([('id', '=', self.dog.id)]))
        own = env_b['kennel.resident'].create({'name': 'Fido', 'partner_id': self.jones.id})
        self.assertEqual(own.company_id, company_b)
        self.assertFalse(self.env(user=self.keeper)['kennel.resident'].search([('id', '=', own.id)]))
        # A company B booking can't use company A's yard.
        booking_b = env_b['kennel.booking'].create({
            'partner_id': self.jones.id, 'resident_ids': [Command.set(own.ids)],
            'arrival_datetime': datetime(2026, 10, 1), 'departure_datetime': datetime(2026, 10, 2),
        })
        with self.assertRaises(Exception):
            booking_b.line_ids.sudo().yard_id = self.run1

    def test_invoicing_setting_needs_accounting_and_inventory(self):
        installed = self.env['ir.module.module'].search_count(
            [('name', 'in', ('account', 'stock')), ('state', '=', 'installed')]) == 2
        settings = self.env['res.config.settings'].create({})
        self.assertEqual(settings.kennel_invoicing_available, installed)
        # The companion module installs itself exactly when both apps are there.
        bridge = self.env['ir.module.module'].search([('name', '=', 'boarding_kennel_manager_invoicing')])
        self.assertEqual(bridge.state == 'installed', installed)

    def test_control_plane_settings(self):
        new_company = self.env['res.company'].create({'name': 'Control Plane Defaults'})
        self.assertEqual(new_company.kennel_cp_theme, 'system')
        self.assertEqual(new_company.kennel_cp_background, 'branding')
        self.assertEqual(new_company.kennel_cp_refresh_minutes, 5)
        settings = self.env['res.config.settings'].create({})
        settings.write({
            'kennel_cp_theme': 'dark', 'kennel_cp_background': 'colour',
            'kennel_cp_colour_light': '#FFFFFF', 'kennel_cp_colour_dark': '#000000',
            'kennel_cp_image_transparency': 40,
        })
        settings.execute()
        company = self.env.company
        self.assertEqual((company.kennel_cp_theme, company.kennel_cp_background), ('dark', 'colour'))
        self.assertEqual((company.kennel_cp_colour_light, company.kennel_cp_colour_dark), ('#FFFFFF', '#000000'))
        self.assertEqual(company.kennel_cp_image_transparency, 40)
        with self.assertRaises(ValidationError):
            company.kennel_cp_image_transparency = 101

from datetime import date

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger
from odoo.tools.safe_eval import safe_eval


@tagged('post_install', '-at_install')
class TestZooManager(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.diet = cls.env['zoo.diet'].create({
            'name': 'Adult Meerkat',
            'line_ids': [(0, 0, {'food': 'Insects', 'quantity': 0.05, 'unit': 'kg'})],
        })
        cls.mammals = cls.env['zoo.animal.class'].create({'name': 'Test Mammals', 'prefix_code': 'QM'})
        cls.species = cls.env['zoo.species'].create({
            'name': 'Meerkat',
            'scientific_name': 'Suricata suricatta',
            'class_id': cls.mammals.id,
            'prefix_code': 'QMK',
            'default_diet_id': cls.diet.id,
        })
        cls.mound = cls.env['zoo.enclosure'].create({'name': 'Meerkat Mound', 'code': 'MM', 'capacity': 2})
        cls.quarantine = cls.env['zoo.enclosure'].create({'name': 'Quarantine', 'code': 'Q1'})
        cls.keeper = new_test_user(cls.env, login='zoo_keeper', groups='zoo_manager.group_zoo_keeper')

    def test_prefix_code_suggestions(self):
        Class = self.env['zoo.animal.class']
        Species = self.env['zoo.species']
        # Initials of the words, else the start of the name.
        self.assertEqual(Species._suggest_prefix_code('Zebra Yak Xerus'), 'ZYX')
        self.assertEqual(Species._suggest_prefix_code('Qed Panda'), 'QPA')
        self.assertEqual(len(Class._suggest_prefix_code('Qwertyfish')), 2)
        # Suggestions skip codes already in use, archived records included.
        Species.create({'name': 'Qxz One', 'prefix_code': 'QXZ', 'active': False})
        self.assertNotEqual(Species._suggest_prefix_code('Qxz'), 'QXZ')
        self.assertTrue(Species._suggest_prefix_code('Qxz').startswith('Q'))

    def test_prefix_code_assigned_on_create(self):
        first, second = self.env['zoo.species'].create([{'name': 'Qqq Alpha'}, {'name': 'Qqq Alpha Two'}])
        self.assertEqual(len(first.prefix_code), 3)
        self.assertEqual(len(second.prefix_code), 3)
        self.assertNotEqual(first.prefix_code, second.prefix_code)
        animal_class = self.env['zoo.animal.class'].create({'name': 'Qqq Class', 'prefix_code': 'qz'})
        self.assertEqual(animal_class.prefix_code, 'QZ')

    def test_prefix_code_validation(self):
        with self.assertRaises(ValidationError):
            self.env['zoo.animal.class'].create({'name': 'Bad', 'prefix_code': 'ABC'})
        with self.assertRaises(ValidationError):
            self.env['zoo.species'].create({'name': 'Bad', 'prefix_code': 'A1B'})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.env['zoo.species'].create({'name': 'Duplicate', 'prefix_code': 'QMK'})

    def test_schedule_species_loaded(self):
        Species = self.env['zoo.species']
        scheduled = Species.search([('species_code', '!=', False)])
        self.assertGreaterEqual(len(scheduled), 377)
        self.assertTrue(all(scheduled.mapped('include_on_annual_return')))
        self.assertEqual(len(set(scheduled.mapped('prefix_code'))), len(scheduled))
        emu = self.env.ref('zoo_manager.zoo_species_1')
        self.assertEqual(emu.name, 'Emu')
        self.assertEqual(emu.class_id, self.env.ref('zoo_manager.zoo_class_birds'))
        self.assertEqual(emu.display_name, '[1] Emu')
        self.assertEqual(Species.name_search('Dromaius')[0][0], emu.id)
        # Two schedule entries share a common name; the codes tell them apart.
        self.assertEqual(Species.search_count([('name', '=', 'Blue Bonnet Parrot')]), 2)
        class_codes = set(self.env['zoo.animal.class'].search([]).mapped('prefix_code'))
        self.assertTrue(class_codes.issuperset({'AM', 'BI', 'MA', 'RE'}))

    def test_animal_class_from_species(self):
        self.assertEqual(self._animal().class_id, self.mammals)

    def test_class_narrows_species(self):
        birds = self.env['zoo.animal.class'].create({'name': 'Test Birds', 'prefix_code': 'QB'})
        parrot = self.env['zoo.species'].create({'name': 'Test Parrot', 'prefix_code': 'QPT', 'class_id': birds.id})
        for model in ('zoo.animal', 'zoo.diet'):
            with self.subTest(model=model):
                form = Form(self.env[model])
                form.name = 'Test'
                # Choosing a species fills in its class.
                form.species_id = self.species
                self.assertEqual(form.class_id, self.mammals)
                # Switching to another class clears a species that doesn't belong to it.
                form.class_id = birds
                self.assertFalse(form.species_id)
                form.species_id = parrot
                record = form.save()
                self.assertEqual(record.class_id, birds)
                # The species list only offers species of the chosen class.
                domain = safe_eval(record._fields['species_id'].domain, {'class_id': record.class_id.id})
                self.assertEqual(self.env['zoo.species'].search(domain), birds.species_ids)

    def _animal(self, **vals):
        return self.env['zoo.animal'].create({'name': 'Kira', 'species_id': self.species.id, **vals})

    def test_reference_and_default_diet(self):
        animal = self._animal()
        self.assertTrue(animal.reference.startswith('ZOO'))
        self.assertEqual(animal.diet_id, self.diet)
        self.assertIn(animal.reference, animal.display_name)

    def test_moves_are_logged(self):
        animal = self._animal(enclosure_id=self.quarantine.id)
        self.assertEqual(len(animal.move_ids), 1)
        self.assertEqual(animal.move_ids.to_enclosure_id, self.quarantine)

        animal.enclosure_id = self.mound
        self.assertEqual(len(animal.move_ids), 2)
        latest = animal.move_ids.filtered(lambda m: m.to_enclosure_id == self.mound)
        self.assertEqual(latest.from_enclosure_id, self.quarantine)

        # Writing the same enclosure again is not a move.
        animal.enclosure_id = self.mound
        self.assertEqual(len(animal.move_ids), 2)

    def test_over_capacity(self):
        for name in ('A', 'B'):
            self._animal(name=name, enclosure_id=self.mound.id)
        self.assertFalse(self.mound.over_capacity)
        self._animal(name='C', enclosure_id=self.mound.id)
        self.assertEqual(self.mound.animal_count, 3)
        self.assertTrue(self.mound.over_capacity)

    def test_age_and_departure(self):
        animal = self._animal(date_of_birth=date(2020, 1, 1))
        self.assertTrue(animal.age)
        animal.state = 'deceased'
        self.assertEqual(animal.departure_date, fields.Date.context_today(animal))
        with self.assertRaises(ValidationError):
            animal.departure_date = date(2019, 1, 1)

    def test_own_parent(self):
        animal = self._animal(sex='female')
        with self.assertRaises(ValidationError):
            animal.dam_id = animal

    def test_latest_weight(self):
        animal = self._animal()
        self.env['zoo.animal.weight'].create([
            {'animal_id': animal.id, 'date': date(2026, 1, 1), 'weight': 0.7},
            {'animal_id': animal.id, 'date': date(2026, 3, 1), 'weight': 0.75},
        ])
        self.assertEqual(animal.latest_weight, 0.75)

    def test_feeding_round(self):
        present = self._animal(enclosure_id=self.mound.id)
        self._animal(name='Gone', enclosure_id=self.mound.id, state='transferred')
        feeding = self.env['zoo.feeding'].create({'enclosure_id': self.mound.id})
        self.assertEqual(feeding.animal_ids, present)
        feeding.action_mark_fed()
        self.assertEqual(feeding.state, 'done')
        self.assertTrue(feeding.fed_datetime)
        self.assertIn(feeding, present.feeding_ids)

    def test_keeper_permissions(self):
        env = self.env(user=self.keeper)
        animal = env['zoo.animal'].create({
            'name': 'Kopi', 'species_id': self.species.id, 'enclosure_id': self.quarantine.id,
        })
        animal.enclosure_id = self.mound.id
        self.assertEqual(len(animal.move_ids), 2)
        env['zoo.health.record'].create({'animal_id': animal.id, 'summary': 'Check-up'})
        env['zoo.animal.weight'].create({'animal_id': animal.id, 'weight': 0.7})
        env['zoo.feeding'].create({'enclosure_id': self.mound.id}).action_mark_fed()

        with self.assertRaises(AccessError):
            env['zoo.species'].create({'name': 'Lemur'})
        with self.assertRaises(AccessError):
            env['zoo.enclosure'].create({'name': 'New Paddock'})
        with self.assertRaises(AccessError):
            animal.move_ids[:1].unlink()
        with self.assertRaises(AccessError):
            animal.unlink()

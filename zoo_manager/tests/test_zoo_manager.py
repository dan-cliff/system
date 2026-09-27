from datetime import date

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestZooManager(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.diet = cls.env['zoo.diet'].create({
            'name': 'Adult Meerkat',
            'line_ids': [(0, 0, {'food': 'Insects', 'quantity': 0.05, 'unit': 'kg'})],
        })
        cls.species = cls.env['zoo.species'].create({
            'name': 'Meerkat',
            'scientific_name': 'Suricata suricatta',
            'animal_class': 'mammal',
            'default_diet_id': cls.diet.id,
        })
        cls.mound = cls.env['zoo.enclosure'].create({'name': 'Meerkat Mound', 'code': 'MM', 'capacity': 2})
        cls.quarantine = cls.env['zoo.enclosure'].create({'name': 'Quarantine', 'code': 'Q1'})
        cls.keeper = new_test_user(cls.env, login='zoo_keeper', groups='zoo_manager.group_zoo_keeper')

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

from datetime import date
from unittest.mock import MagicMock, call, patch

import pytz

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger
from odoo.tools.safe_eval import safe_eval

from ..lib import taxonomy_lookup

PIXEL_PNG = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='


@tagged('post_install', '-at_install')
class TestZooManager(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.insects = cls.env['product.product'].create({'name': 'Test Insects', 'is_storable': True})
        cls.diet = cls.env['zoo.diet'].create({
            'name': 'Adult Meerkat',
            'line_ids': [(0, 0, {'product_id': cls.insects.id, 'quantity': 0.05})],
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

    def test_feed_products_follow_settings(self):
        company = self.env.company
        Product = self.env['product.product']
        feed_categ = self.env['product.category'].create({'name': 'Test Feed'})
        pellets_categ = self.env['product.category'].create({'name': 'Test Pellets', 'parent_id': feed_categ.id})
        other_categ = self.env['product.category'].create({'name': 'Test Not Feed'})
        feed_wh = self.env['stock.warehouse'].create({'name': 'Test Feed Store', 'code': 'TFS'})
        other_wh = self.env['stock.warehouse'].create({'name': 'Test Shop', 'code': 'TSH'})

        def product(name, categ, warehouse):
            record = Product.create({'name': name, 'categ_id': categ.id, 'is_storable': True})
            self.env['stock.quant']._update_available_quantity(record, warehouse.lot_stock_id, 10)
            return record

        hay = product('Test Hay', feed_categ, feed_wh)
        pellets = product('Test Pellets', pellets_categ, feed_wh)  # sub-category counts
        feed_elsewhere = product('Test Seed', feed_categ, other_wh)
        not_feed = product('Test Mug', other_categ, feed_wh)
        mine = hay | pellets | feed_elsewhere | not_feed

        company.write({'zoo_feed_warehouse_ids': [(6, 0, feed_wh.ids)], 'zoo_feed_categ_ids': [(6, 0, feed_categ.ids)]})
        for record in (self.env['zoo.diet.line'].new({}), self.env['zoo.feeding.line'].new({})):
            with self.subTest(model=record._name):
                offered = Product.search(record.product_domain) & mine
                self.assertEqual(offered, hay | pellets)

        # Only categories set: any warehouse.
        company.zoo_feed_warehouse_ids = False
        offered = Product.search(self.env['zoo.diet.line'].new({}).product_domain) & mine
        self.assertEqual(offered, hay | pellets | feed_elsewhere)

        # Nothing set: no filtering.
        company.zoo_feed_categ_ids = False
        self.assertEqual(self.env['zoo.feeding.line'].new({}).product_domain, [])

    def test_dates_are_day_first(self):
        self.assertEqual(self.env.ref('base.lang_en').date_format, '%d/%m/%Y')
        feeding = self.env['zoo.feeding'].create({
            'enclosure_id': self.mound.id,
            'scheduled_datetime': '2026-03-04 09:30:00',
        })
        # 4 March, day first (09:30 UTC is 4 March in any timezone within ±9h).
        self.assertIn('04/03/2026', feeding.display_name)

    def test_feeding_takes_feed_out_of_stock(self):
        warehouse = self.env['stock.warehouse'].create({'name': 'Test Feed Barn', 'code': 'TFB'})
        stock = warehouse.lot_stock_id
        Quant = self.env['stock.quant']
        crickets = self.env['product.product'].create({'name': 'Test Crickets', 'is_storable': True})
        water = self.env['product.product'].create({'name': 'Test Water', 'type': 'consu'})  # not tracked
        Quant._update_available_quantity(self.insects, stock, 10)
        Quant._update_available_quantity(crickets, stock, 100)
        self.diet.line_ids = [(0, 0, {'product_id': crickets.id, 'quantity': 5}),
                              (0, 0, {'product_id': water.id, 'quantity': 1})]
        self._animal(name='A', enclosure_id=self.mound.id)
        self._animal(name='B', enclosure_id=self.mound.id)

        feeding = self.env['zoo.feeding'].create({'enclosure_id': self.mound.id, 'warehouse_id': warehouse.id})
        # Food lines come from both animals' diets, added up per product.
        given = {line.product_id: line.quantity for line in feeding.line_ids}
        self.assertEqual(given, {self.insects: 0.1, crickets: 10, water: 2})

        feeding.line_ids.filtered(lambda l: l.product_id == crickets).quantity = 12  # what was actually given
        feeding.action_mark_fed()
        self.assertEqual(feeding.state, 'done')
        self.assertAlmostEqual(Quant._get_available_quantity(self.insects, stock), 9.9)
        self.assertEqual(Quant._get_available_quantity(crickets, stock), 88)
        self.assertEqual(len(feeding.move_ids), 2)  # water isn't tracked in inventory
        self.assertTrue(all(m.state == 'done' for m in feeding.move_ids))
        self.assertEqual(feeding.move_ids.location_dest_id, self.env.company.zoo_feed_location_id)

        # Resetting puts the stock back; marking fed again takes it out again.
        feeding.action_reset_to_planned()
        self.assertAlmostEqual(Quant._get_available_quantity(self.insects, stock), 10)
        self.assertEqual(Quant._get_available_quantity(crickets, stock), 100)
        feeding.action_mark_fed()
        self.assertEqual(Quant._get_available_quantity(crickets, stock), 88)
        feeding.action_cancel()
        self.assertEqual(feeding.state, 'cancelled')
        self.assertEqual(Quant._get_available_quantity(crickets, stock), 100)

    def test_keeper_can_mark_fed(self):
        warehouse = self.env['stock.warehouse'].create({'name': 'Test Keeper Barn', 'code': 'TKB'})
        self.env['stock.quant']._update_available_quantity(self.insects, warehouse.lot_stock_id, 5)
        self._animal(enclosure_id=self.mound.id)
        feeding = self.env['zoo.feeding'].with_user(self.keeper).create(
            {'enclosure_id': self.mound.id, 'warehouse_id': warehouse.id})
        feeding.action_mark_fed()
        self.assertEqual(self.env['stock.quant']._get_available_quantity(self.insects, warehouse.lot_stock_id), 4.95)

    def test_choice_lists_are_records(self):
        emu = self.env.ref('zoo_manager.zoo_species_1')
        self.assertEqual(emu.conservation_status_id, self.env.ref('zoo_manager.zoo_conservation_status_lc'))
        record = self.env['zoo.health.record'].create({'animal_id': self._animal().id, 'summary': 'Check'})
        self.assertEqual(record.record_type_id, self.env.ref('zoo_manager.zoo_health_record_type_checkup'))
        self.assertEqual(self.diet.line_ids[:1].frequency_id, self.env.ref('zoo_manager.zoo_diet_frequency_daily'))
        self.assertTrue(self.env.ref('zoo_manager.zoo_feeding_consumption_none').refused)

    def test_species_lookup_fills_only_empty_fields(self):
        classification = {'kingdom': 'Animalia', 'phylum': 'Chordata', 'class': 'Mammalia', 'order': 'Diprotodontia',
                          'family': 'Macropodidae', 'genus': 'Macropus', 'species': 'Macropus giganteus'}
        pictures = {'image': PIXEL_PNG, 'distribution': PIXEL_PNG, 'url': 'https://en.wikipedia.org/wiki/Eastern_grey_kangaroo'}
        species = self.env['zoo.species'].create({
            'name': 'Test Kangaroo', 'prefix_code': 'QKG', 'scientific_name': 'Macropus giganteus',
            'taxon_genus': 'Kept Genus',
        })
        self.assertTrue(species.lookup_pending)
        with patch.object(taxonomy_lookup, 'lookup_classification', return_value=classification), \
             patch.object(taxonomy_lookup, 'lookup_images', return_value=pictures):
            species._lookup_classification()
        self.assertFalse(species.lookup_pending)
        self.assertEqual(species.taxon_class, 'Mammalia')
        self.assertEqual(species.taxon_species, 'Macropus giganteus')
        self.assertEqual(species.taxon_genus, 'Kept Genus')  # never overwritten
        self.assertTrue(species.image and species.distribution_image)
        self.assertEqual(species.reference_url, pictures['url'])

        # A complete species isn't queued; changing the scientific name re-queues a partial one.
        self.assertFalse(self.env['zoo.species'].create({
            'name': 'Complete', 'prefix_code': 'QCP', 'scientific_name': 'Macropus giganteus', 'reference_url': 'x',
            **{field: 'x' for field in ('taxon_kingdom', 'taxon_phylum', 'taxon_class', 'taxon_order',
                                        'taxon_family', 'taxon_genus', 'taxon_species')},
            'image': PIXEL_PNG, 'distribution_image': PIXEL_PNG,
        }).lookup_pending)
        species.image = False
        species.scientific_name = 'Macropus fuliginosus'
        self.assertTrue(species.lookup_pending)

    def test_nightly_check_looks_up_missing_classification(self):
        classification = {'kingdom': 'Animalia', 'class': 'Reptilia', 'order': 'Squamata', 'family': 'Pythonidae',
                          'phylum': 'Chordata', 'genus': 'Morelia', 'species': 'Morelia spilota'}
        Species = self.env['zoo.species']
        python = Species.create({'name': 'Test Python', 'prefix_code': 'QPY', 'scientific_name': 'Morelia spilota',
                                 'taxon_class': 'Reptilia'})
        no_name = Species.create({'name': 'Unnamed', 'prefix_code': 'QUN'})
        no_commit = patch.object(type(self.env['ir.cron']), '_commit_progress', return_value=60.0)
        with no_commit, patch.object(taxonomy_lookup, 'lookup_images', return_value={}), \
             patch.object(taxonomy_lookup, 'lookup_classification', return_value=classification) as lookup:
            Species._cron_nightly_classification_check()
            self.assertIn(call('Morelia spilota'), lookup.call_args_list)
            self.assertEqual(python.taxon_order, 'Squamata')
            self.assertTrue(python.lookup_checked)
            self.assertFalse(no_name.lookup_checked)
            # Already checked tonight: a rerun leaves it alone.
            python.taxon_family = False
            lookup.reset_mock()
            Species._cron_nightly_classification_check()
            self.assertNotIn(call('Morelia spilota'), lookup.call_args_list)

        # Rate limited: the species isn't counted as a failure and is tried again later.
        python.write({'lookup_pending': True, 'lookup_failures': 0})
        with no_commit, patch.object(self.env.cr, 'rollback'), \
             patch.object(taxonomy_lookup, 'lookup_classification', side_effect=taxonomy_lookup.RateLimited('x')):
            Species.search([('id', '!=', python.id)]).lookup_pending = False
            Species._cron_lookup_classification()
        self.assertEqual(python.lookup_failures, 0)
        self.assertTrue(python.lookup_pending)

        cron = self.env.ref('zoo_manager.ir_cron_zoo_species_nightly_check')
        cron.user_id.tz = 'Australia/Melbourne'
        Species._schedule_nightly_classification_check()
        local = pytz.utc.localize(cron.nextcall).astimezone(pytz.timezone('Australia/Melbourne'))
        self.assertEqual((local.hour, local.minute), (3, 0))

    def _fake_get(self, payload):
        response = MagicMock()
        response.json.return_value = payload
        return patch.object(taxonomy_lookup, '_get', return_value=response)

    def test_classification_needs_exact_gbif_match(self):
        match = {'matchType': 'EXACT', 'confidence': 99, 'kingdom': 'Animalia', 'class': 'Aves', 'species': 'Dromaius novaehollandiae'}
        with self._fake_get(match):
            self.assertEqual(taxonomy_lookup.lookup_classification('Dromaius novaehollandiae'),
                             {'kingdom': 'Animalia', 'class': 'Aves', 'species': 'Dromaius novaehollandiae'})
        with self._fake_get(dict(match, matchType='FUZZY')):
            self.assertEqual(taxonomy_lookup.lookup_classification('Dromaius novaehollandae'), {})
        with self._fake_get(dict(match, confidence=80)):
            self.assertEqual(taxonomy_lookup.lookup_classification('Dromaius novaehollandiae'), {})
        self.assertEqual(taxonomy_lookup.lookup_classification('Phasianus spp'), {})
        python = {'matchType': 'EXACT', 'confidence': 99, 'class': 'Squamata', 'family': 'Pythonidae'}
        with self._fake_get(python):
            self.assertEqual(taxonomy_lookup.lookup_classification('Morelia spilota'),
                             {'class': 'Reptilia', 'order': 'Squamata', 'family': 'Pythonidae'})
        with self._fake_get(dict(python, order='Testudines', **{'class': 'Testudines'})):
            self.assertEqual(taxonomy_lookup.lookup_classification('Chelodina longicollis')['class'], 'Reptilia')
        response = MagicMock(status_code=429, headers={'Retry-After': '1'})
        with patch.object(taxonomy_lookup.requests, 'get', return_value=response) as get, \
             patch.object(taxonomy_lookup.time, 'sleep'), self.assertRaises(taxonomy_lookup.RateLimited):
            taxonomy_lookup._get('https://upload.wikimedia.org/x.jpg')
        self.assertEqual(get.call_count, taxonomy_lookup.RETRIES + 1)
        self.assertEqual(taxonomy_lookup.clean_name('Calyptorhynchus banksii (except graptogyne)'), 'Calyptorhynchus banksii')

    def test_distribution_map_is_image_after_binomial_name(self):
        infobox = '''<table class="infobox biota">
            <tr><td><img src="//upload.wikimedia.org/thumb/a/ab/Kangaroo.jpg/250px-Kangaroo.jpg"/></td></tr>
            <tr><th>Scientific classification</th></tr>
            <tr><th>Binomial name</th></tr>
            <tr><td><i>Macropus giganteus</i></td></tr>
            <tr><td><img src="//upload.wikimedia.org/thumb/c/cd/Range.png/220px-Range.png"/></td></tr>
            <tr><th>Synonyms</th></tr>
        </table>'''
        with self._fake_get({'parse': {'text': infobox}}):
            src = taxonomy_lookup._distribution_map_src('Eastern grey kangaroo')
        self.assertEqual(src, '//upload.wikimedia.org/thumb/c/cd/Range.png/220px-Range.png')
        self.assertEqual(taxonomy_lookup._larger_thumbnail(src, 800), '//upload.wikimedia.org/thumb/c/cd/Range.png/800px-Range.png')
        with self._fake_get({'parse': {'text': '<table class="infobox biota"><tr><th>Binomial name</th></tr></table>'}}):
            self.assertIsNone(taxonomy_lookup._distribution_map_src('No map'))

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

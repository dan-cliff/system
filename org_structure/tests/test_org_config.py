from lxml import etree

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOrgConfig(TransactionCase):

    def _settings(self, **values):
        self.env['res.config.settings'].create(values).execute()

    def test_defaults(self):
        config = self.env['org.config']._get_config()
        self.assertTrue(all(config[level]['enabled'] for level in config))
        self.assertEqual(config['department']['parent'], 'location')
        self.assertEqual(config['business_unit']['label'], 'Business Unit')
        self.assertFalse(self.env.ref('org_structure.menu_org_division', raise_if_not_found=False))

    def test_relabel_everywhere(self):
        self._settings(org_division_label='Region', org_division_plural='Regions')
        users_fields = self.env['res.users'].fields_get(['home_division_id', 'org_scope_division'])
        self.assertEqual(users_fields['home_division_id']['string'], 'Home Region')
        self.assertEqual(users_fields['org_scope_division']['string'], 'Scope all apps to this Region')
        self.assertEqual(self.env['org.location'].fields_get(['division_id'])['division_id']['string'], 'Region')
        self.assertEqual(
            self.env['res.users.org.scope'].fields_get(['effective_division_ids'])['effective_division_ids']['string'],
            'Regions')
        self.assertEqual(self.env['res.partner'].fields_get(['org_division_id'])['org_division_id']['string'], 'Region')
        self.assertEqual(self.env.ref('org_structure.action_org_division').name, 'Regions')
        # Other fields that merely use the same words are left alone.
        self.assertEqual(self.env['res.users'].fields_get(['name'])['name']['string'], 'Name')
        # Views: the Organisation tab and settings block read "Region(s)".
        arch = self.env['res.users'].get_view(self.env.ref('base.view_users_form').id, 'form')['arch']
        page = etree.fromstring(arch).xpath("//page[@name='org_structure']")[0]
        self.assertNotIn('Division', etree.tostring(page, encoding='unicode'))
        settings = etree.fromstring(self.env['res.config.settings'].get_view(view_type='form')['arch'])
        block = settings.xpath("//block[@name='org_structure_settings']")[0]
        self.assertTrue(block.xpath(".//button[@string='Regions']"))
        self.assertTrue(block.xpath(".//setting[@string='Regions']"))
        # The field itself keeps its technical name.
        self.assertIn('home_division_id', self.env['res.users']._fields)

    def test_disable_level(self):
        self._settings(org_business_unit_enabled=False)
        config = self.env['org.config']
        self.assertEqual(config._parent_level('location'), 'division')
        division = self.env['org.division'].create({'name': 'D'})
        location = self.env['org.location'].create({'name': 'L', 'division_id': division.id})
        self.assertEqual(location.org_parent_level, 'division')
        self.assertEqual(location.company_id, division.company_id)
        with self.assertRaises(ValidationError):
            self.env['org.location'].create({'name': 'Orphan'})
        # Hidden on the user form and in the automatic sections.
        arch = etree.fromstring(
            self.env['res.users'].get_view(self.env.ref('base.view_users_form').id, 'form')['arch'])
        self.assertEqual(arch.xpath("//field[@name='home_business_unit_id']")[0].get('invisible'), '1')
        self.assertEqual(arch.xpath("//div[contains(@class, 'o_org_level_business_unit')]")[0].get('invisible'), '1')
        self.env['org.business.unit'].create({'name': 'B', 'division_id': division.id})
        self.assertFalse(self.env.user.org_show_business_unit)
        self.assertTrue(self.env.user.org_show_location)

    def test_keep_one_level(self):
        with self.assertRaises(ValidationError):
            self._settings(org_division_enabled=False, org_business_unit_enabled=False,
                           org_location_enabled=False, org_department_enabled=False)

    def test_department_under_business_unit(self):
        self._settings(org_department_parent='business_unit')
        division = self.env['org.division'].create({'name': 'D'})
        bu = self.env['org.business.unit'].create({'name': 'B', 'division_id': division.id})
        dept = self.env['org.department'].create({'name': 'Dept', 'business_unit_id': bu.id})
        self.assertEqual(dept.division_id, division)
        self.assertFalse(dept.location_id)
        with self.assertRaises(ValidationError):
            self.env['org.department'].create({'name': 'No BU'})
        # Users and records take the levels above from the department.
        user = self.env['res.users'].create({'name': 'U', 'login': 'org_cfg_u'})
        user.write({'home_department_id': dept.id, 'home_business_unit_id': bu.id,
                    'home_division_id': division.id})
        partner = self.env['res.partner'].create({'name': 'P', 'org_department_id': dept.id})
        self.assertEqual(partner.org_business_unit_id, bu)
        self.assertEqual(partner.org_division_id, division)
        self.assertFalse(partner.org_location_id)

from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOrgStructure(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.div_a = cls.env['org.division'].create({'name': 'Division A'})
        cls.div_b = cls.env['org.division'].create({'name': 'Division B'})
        cls.bu_a = cls.env['org.business.unit'].create({'name': 'BU A', 'division_id': cls.div_a.id})
        cls.bu_b = cls.env['org.business.unit'].create({'name': 'BU B', 'division_id': cls.div_b.id})
        cls.loc_a = cls.env['org.location'].create({'name': 'Loc A', 'business_unit_id': cls.bu_a.id})
        cls.loc_b = cls.env['org.location'].create({'name': 'Loc B', 'business_unit_id': cls.bu_b.id})
        cls.dept_a = cls.env['org.department'].create({'name': 'Dept A', 'location_id': cls.loc_a.id})
        cls.user = cls.env['res.users'].create({'name': 'Scoped User', 'login': 'org_scoped_user'})
        cls.app = cls.env['ir.ui.menu'].search([('parent_id', '=', False), ('web_icon', '!=', False)], limit=1)

    def test_parents_and_company_inherited(self):
        self.assertEqual(self.dept_a.location_id, self.loc_a)
        self.assertEqual(self.dept_a.business_unit_id, self.bu_a)
        self.assertEqual(self.dept_a.division_id, self.div_a)
        self.assertEqual(self.dept_a.company_id, self.company)
        # Moving a business unit carries everything below it along.
        other_company = self.env['res.company'].create({'name': 'Other Co'})
        div_c = self.env['org.division'].create({'name': 'Division C', 'company_id': other_company.id})
        self.bu_a.division_id = div_c
        self.assertEqual(self.loc_a.division_id, div_c)
        self.assertEqual(self.dept_a.division_id, div_c)
        self.assertEqual(self.dept_a.company_id, other_company)

    def test_home_units_fill_and_clear(self):
        with Form(self.user.with_user(self.env.ref('base.user_admin')), view='base.view_users_form') as form:
            form.home_department_id = self.dept_a
            self.assertEqual(form.home_location_id, self.loc_a)
            self.assertEqual(form.home_business_unit_id, self.bu_a)
            self.assertEqual(form.home_division_id, self.div_a)
            form.home_division_id = self.div_b
            self.assertFalse(form.home_business_unit_id)
            self.assertFalse(form.home_location_id)
            self.assertFalse(form.home_department_id)

    def test_home_units_must_nest(self):
        with self.assertRaises(ValidationError):
            self.user.write({'home_division_id': self.div_b.id, 'home_business_unit_id': self.bu_a.id})

    def test_only_one_scope_level(self):
        self.user.write({'home_department_id': self.dept_a.id, 'home_location_id': self.loc_a.id,
                         'home_business_unit_id': self.bu_a.id, 'home_division_id': self.div_a.id})
        with Form(self.user.with_user(self.env.ref('base.user_admin')), view='base.view_users_form') as form:
            form.org_scope_division = True
            self.assertEqual(form.org_scope_level, 'division')
            form.org_scope_location = True
            self.assertEqual(form.org_scope_level, 'location')
            self.assertFalse(form.org_scope_division)
        self.assertEqual(self.user.org_scope_level, 'location')
        self.assertTrue(self.user.org_scope_location)
        self.assertFalse(self.user.org_scope_division)
        # Writing several flags at once: the newly ticked one wins.
        self.user.write({'org_scope_department': True, 'org_scope_location': True})
        self.assertEqual(self.user.org_scope_level, 'department')
        self.user.org_scope_department = False
        self.assertFalse(self.user.org_scope_level)

    def test_scope_needs_home_unit(self):
        with self.assertRaises(ValidationError):
            self.user.org_scope_division = True

    def test_global_scope_domain(self):
        self.assertIsNone(self.user._get_org_scope_domain('res.partner'))
        self.user.write({'home_division_id': self.div_a.id, 'org_scope_division': True})
        self.assertEqual(
            self.user._get_org_scope_domain('res.partner'),
            Domain('org_division_id', '=', self.div_a.id) | Domain('org_division_id', '=', False),
        )

    def test_app_scope_cumulative(self):
        line = self.user.org_app_scope_ids.filtered(lambda l: l.menu_id == self.app)
        line.write({
            'division_ids': [(6, 0, self.div_a.ids)],
            'location_ids': [(6, 0, self.loc_b.ids)],
        })
        self.assertEqual(line.effective_division_ids, self.div_a)
        self.assertEqual(line.effective_location_ids, self.loc_b)
        app_models = line._get_app_models()
        if not app_models:
            return
        model = next(iter(app_models))
        self.assertEqual(
            self.user._get_org_scope_domain(model),
            Domain('org_division_id', 'in', self.div_a.ids)
            | Domain('org_location_id', 'in', self.loc_b.ids)
            | Domain('org_division_id', '=', False),
        )
        # An app with no units selected is unscoped.
        line.write({'division_ids': [(5,)], 'location_ids': [(5,)]})
        self.assertIsNone(self.user._get_org_scope_domain(model))

    def test_scope_all_apps_overrides_app_scope(self):
        line = self.user.org_app_scope_ids.filtered(lambda l: l.menu_id == self.app)
        line.write({'division_ids': [(6, 0, self.div_b.ids)], 'location_ids': [(6, 0, self.loc_b.ids)]})
        self.user.write({'home_department_id': self.dept_a.id, 'home_location_id': self.loc_a.id,
                         'home_business_unit_id': self.bu_a.id, 'home_division_id': self.div_a.id,
                         'org_scope_location': True})
        # Every app shows the all-apps rule instead of its own units...
        self.assertTrue(line.scoped_all_apps)
        self.assertEqual(line.effective_location_ids, self.loc_a)
        self.assertFalse(line.effective_division_ids)
        self.assertFalse(line.effective_business_unit_ids)
        self.assertFalse(line.effective_department_ids)
        # ...and that rule is what gets enforced, for every model.
        expected = Domain('org_location_id', '=', self.loc_a.id) | Domain('org_division_id', '=', False)
        for model in line._get_app_models() | {'res.partner'}:
            self.assertEqual(self.user._get_org_scope_domain(model), expected)
        # The app's own units are kept and come back once unticked.
        self.user.org_scope_location = False
        self.assertFalse(line.scoped_all_apps)
        self.assertEqual(line.effective_division_ids, self.div_b)
        self.assertEqual(line.effective_location_ids, self.loc_b)

    def test_ticking_scope_shows_rule_on_apps_in_form(self):
        self.user.write({'home_division_id': self.div_a.id})
        admin = self.env.ref('base.user_admin')
        with Form(self.user.with_user(admin), view='base.view_users_form') as form:
            form.org_scope_division = True
            for row in form.org_app_scope_ids._records:
                self.assertEqual(row['effective_division_ids'], self.div_a.ids)

    def test_app_list_alphabetical(self):
        self.env['ir.ui.menu'].create({'name': 'AAA App', 'web_icon': 'org_structure,static/description/icon.png'})
        self.env.invalidate_all()
        names = self.user.org_app_scope_ids.mapped('app_name')
        self.assertEqual(names[0], 'AAA App')
        self.assertEqual(names, sorted(names))

    def test_app_list_prefilled_with_all_apps(self):
        apps = self.env['ir.ui.menu'].search([('parent_id', '=', False), ('web_icon', '!=', False)])
        self.assertTrue(apps)
        self.assertCountEqual(self.user.org_app_scope_ids.menu_id.ids, apps.ids)
        # Installing a new app adds it to every internal user's list.
        new_app = self.env['ir.ui.menu'].create({
            'name': 'New App', 'web_icon': 'org_structure,static/description/icon.png'})
        self.assertIn(new_app, self.user.org_app_scope_ids.menu_id)
        admin = self.env.ref('base.user_admin')
        self.assertIn(new_app, admin.org_app_scope_ids.menu_id)
        # Plain (non-app) menus are not listed, and removed apps drop out.
        sub_menu = self.env['ir.ui.menu'].create({'name': 'Sub', 'parent_id': new_app.id})
        self.assertNotIn(sub_menu, self.user.org_app_scope_ids.menu_id)
        new_app.unlink()
        self.env.invalidate_all()
        self.assertCountEqual(self.user.org_app_scope_ids.menu_id.ids, apps.ids)

    def test_portal_users_have_no_app_list(self):
        portal = self.env['res.users'].create({
            'name': 'Portal', 'login': 'org_portal_user',
            'group_ids': [(6, 0, self.env.ref('base.group_portal').ids)]})
        self.assertFalse(portal.org_app_scope_ids)
        portal.write({'group_ids': [(6, 0, self.env.ref('base.group_user').ids)]})
        self.assertTrue(portal.org_app_scope_ids)

    def test_form_section_placement(self):
        from lxml import etree
        Model = self.env['res.users.org.scope']
        with_notebook = etree.fromstring('<form><sheet><group/><notebook/></sheet></form>')
        Model._org_add_form_section(with_notebook)
        section = with_notebook.xpath('//group[@name="org_structure"]')[0]
        self.assertEqual(section.getnext().tag, 'notebook')
        self.assertEqual(section.get('invisible'), 'not org_show_division')
        self.assertEqual(
            [f.get('name') for f in section if f.get('invisible') != '1'],
            ['org_division_id', 'org_business_unit_id', 'org_location_id', 'org_department_id'])
        self.assertEqual(section.xpath('field[@name="org_location_id"]')[0].get('invisible'),
                         'not org_show_location')
        plain = etree.fromstring('<form><group/></form>')
        Model._org_add_form_section(plain)
        self.assertEqual(plain[-1].get('name'), 'org_structure')

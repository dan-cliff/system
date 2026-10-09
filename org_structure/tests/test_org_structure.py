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
        cls.app = cls.env['ir.ui.menu'].search([('parent_id', '=', False)], limit=1)

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

    def test_app_scope_cumulative_and_overrides_global(self):
        self.user.write({'home_division_id': self.div_a.id, 'org_scope_division': True})
        line = self.env['res.users.org.scope'].create({
            'user_id': self.user.id,
            'menu_id': self.app.id,
            'division_ids': [(6, 0, self.div_a.ids)],
            'location_ids': [(6, 0, self.loc_b.ids)],
        })
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
        # An app scope line with no units falls back to the global scope.
        line.write({'division_ids': [(5,)], 'location_ids': [(5,)]})
        self.assertEqual(
            self.user._get_org_scope_domain(model),
            Domain('org_division_id', '=', self.div_a.id) | Domain('org_division_id', '=', False),
        )

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBulkUpdateOrg(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.div_a = cls.env['org.division'].create({'name': 'Division A'})
        cls.div_b = cls.env['org.division'].create({'name': 'Division B'})
        cls.bu_a = cls.env['org.business.unit'].create({'name': 'BU A', 'division_id': cls.div_a.id})
        cls.bu_b = cls.env['org.business.unit'].create({'name': 'BU B', 'division_id': cls.div_b.id})
        cls.loc_a = cls.env['org.location'].create({'name': 'Loc A', 'business_unit_id': cls.bu_a.id})
        cls.dept_a = cls.env['org.department'].create({'name': 'Dept A', 'location_id': cls.loc_a.id})
        Ticket = cls.env['dev.ticket']
        cls.t1 = Ticket.create({'name': 'One', 'org_department_id': cls.dept_a.id})
        cls.t2 = Ticket.create({'name': 'Two', 'org_division_id': cls.div_b.id})

    def _apply(self, **vals):
        tickets = self.t1 | self.t2
        self.env['dev.ticket.bulk.update'].with_context(active_ids=tickets.ids).create(vals).action_apply()

    def test_wizard_not_defaulted_or_scoped(self):
        wizard = self.env['dev.ticket.bulk.update'].create({})
        self.assertFalse(wizard.org_division_id)
        self.assertFalse(wizard._org_scoped)

    def test_set_lower_unit_fills_levels_above(self):
        self._apply(update_org=True, org_location_id=self.loc_a.id)
        for ticket in self.t1 | self.t2:
            self.assertEqual((ticket.org_division_id, ticket.org_business_unit_id, ticket.org_location_id),
                             (self.div_a, self.bu_a, self.loc_a))
        self.assertEqual(self.t1.org_department_id, self.dept_a, 'A unit below that still belongs is kept')

    def test_higher_level_clears_units_that_do_not_belong(self):
        self._apply(update_org=True, org_division_id=self.div_b.id)
        self.assertEqual(self.t1.org_division_id, self.div_b)
        self.assertFalse(self.t1.org_business_unit_id or self.t1.org_location_id or self.t1.org_department_id)

    def test_unticked_or_cleared(self):
        self._apply(org_division_id=self.div_b.id)
        self.assertEqual(self.t1.org_department_id, self.dept_a, 'Not ticked: unchanged')
        self._apply(update_org=True)
        self.assertFalse(self.t1.org_division_id | self.t2.org_division_id)
        self.assertFalse(self.t1.org_department_id)

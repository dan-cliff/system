# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPropertyChecklists(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.company = cls.env.company
        cls.inspections = cls.env['checklist.group'].create({'name': 'Property Inspections'})
        cls.vehicles = cls.env['checklist.group'].create({'name': 'Vehicles'})
        cls.inspection = cls.env['checklist.template'].create({
            'name': 'Routine Inspection', 'group_ids': [Command.set(cls.inspections.ids)]})
        cls.prestart = cls.env['checklist.template'].create({
            'name': 'Vehicle Pre-start', 'group_ids': [Command.set(cls.vehicles.ids)]})
        cls.prop = cls.env['property.property'].create({'name': 'Rental House', 'ownership': 'owned_leased_out'})

    def _checklist(self, template):
        return self.env['checklist.checklist'].create({'template_id': template.id, 'user_id': self.env.user.id})

    def test_property_field_only_for_linked_groups(self):
        checklist = self._checklist(self.inspection)
        self.assertFalse(checklist.property_visible, 'Not integrated yet.')
        self.assertFalse(self.prop.property_checklist_enabled)
        self.company.write({'property_checklist_enabled': True,
                            'property_checklist_group_ids': [Command.set(self.inspections.ids)]})
        checklist.invalidate_recordset(['property_visible'])
        self.assertTrue(checklist.property_visible)
        self.assertFalse(self._checklist(self.prestart).property_visible)
        self.prop.invalidate_recordset(['property_checklist_enabled'])
        self.assertTrue(self.prop.property_checklist_enabled)
        # Switched off again: hidden, whatever the groups
        self.company.property_checklist_enabled = False
        checklist.invalidate_recordset(['property_visible'])
        self.assertFalse(checklist.property_visible)

    def test_property_lists_its_checklists(self):
        self.company.write({'property_checklist_enabled': True,
                            'property_checklist_group_ids': [Command.set(self.inspections.ids)]})
        checklist = self._checklist(self.inspection)
        checklist.property_id = self.prop
        self.assertEqual(self.prop.checklist_count, 1)
        action = self.prop.action_view_checklists()
        self.assertEqual(self.env['checklist.checklist'].search(action['domain']), checklist)
        self.assertEqual(action['context']['default_property_id'], self.prop.id)

    def test_changing_template_clears_property(self):
        self.company.write({'property_checklist_enabled': True,
                            'property_checklist_group_ids': [Command.set(self.inspections.ids)]})
        with Form(self.env['checklist.checklist']) as form:
            form.template_id = self.inspection
            form.property_id = self.prop
            form.template_id = self.prestart
            self.assertFalse(form.property_id)

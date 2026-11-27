# -*- coding: utf-8 -*-
from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.advanced_manufacturing.tests.common import ManufacturingCase


@tagged('post_install', '-at_install')
class TestQaChecklists(ManufacturingCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.qa_group = cls.env['checklist.group'].create({'name': 'Test Manufacturing QA'})
        cls.other_group = cls.env['checklist.group'].create({'name': 'Test Vehicle Checks'})
        cls.template = cls.env['checklist.template'].create({
            'name': 'Final Inspection',
            'group_ids': [Command.set(cls.qa_group.ids)],
            'question_ids': [
                Command.create({'name': 'Product', 'question_type': 'text', 'sequence': 1}),
                Command.create({'name': 'Batch Number', 'question_type': 'text', 'sequence': 2}),
                Command.create({'name': 'Quantity', 'question_type': 'number', 'sequence': 3}),
                Command.create({'name': 'Production Date', 'question_type': 'date', 'sequence': 4}),
                Command.create({'name': 'Lot', 'question_type': 'many2one', 'sequence': 5,
                                'relation_model_id': cls.env['ir.model']._get('stock.lot').id}),
                Command.create({'name': 'Finish OK?', 'question_type': 'boolean', 'sequence': 6}),
                Command.create({'name': 'Comments', 'question_type': 'text_area', 'sequence': 7}),
            ],
        })
        cls.other_template = cls.env['checklist.template'].create({
            'name': 'Vehicle Pre-start', 'group_ids': [Command.set(cls.other_group.ids)]})
        cls.company.mrp_qa_checklist_group_ids = cls.qa_group

    def _question(self, name):
        return self.template.question_ids.filtered(lambda q: q.name == name)

    def test_config_lists_qa_templates(self):
        qa = self.workcenter._terminal_config()['features']['qa']
        self.assertEqual([t['id'] for t in qa['templates']], [self.template.id])
        questions = {q['name']: q for q in qa['templates'][0]['questions']}
        self.assertEqual(questions['Product']['prefill'], 'text_product')
        self.assertEqual(questions['Batch Number']['prefill'], 'text_lot')
        self.assertEqual(questions['Quantity']['prefill'], 'quantity')
        self.assertEqual(questions['Production Date']['prefill'], 'date')
        self.assertEqual(questions['Lot']['prefill'], 'lot')
        self.assertIsNone(questions['Comments']['prefill'])
        # No groups chosen: no QA on the app.
        self.company.mrp_qa_checklist_group_ids = False
        self.assertNotIn('qa', self.workcenter._terminal_config()['features'])

    def test_qa_checklist_linked_and_filled(self):
        production = self._production(product=self.lot_product, qty=4)
        workorder = production.workorder_ids
        self._event('produce', workorder, qty=4, lot='WAX-26-01')
        answers = {
            str(self._question('Finish OK?').id): {'value': True},
            str(self._question('Comments').id): {'value': 'Smooth finish'},
        }
        result = self._event('qa', workorder, template_id=self.template.id, state='done', answers=answers)
        self.assertEqual(result['status'], 'ok', result)
        checklist = self.env['checklist.checklist'].search([('production_id', '=', production.id)])
        self.assertEqual(len(checklist), 1)
        self.assertEqual(checklist.state, 'done')
        self.assertEqual(checklist.mrp_product_id, self.lot_product)
        self.assertEqual(checklist.mrp_lot_ids.name, 'WAX-26-01')
        self.assertEqual(checklist.workorder_id, workorder)
        self.assertEqual(checklist.workcenter_id, self.workcenter)
        self.assertEqual(checklist.mrp_employee_id, self.alice)
        lines = {line.name: line for line in checklist.line_ids}
        self.assertEqual(lines['Product'].value_text, 'Candle Batch')
        self.assertEqual(lines['Batch Number'].value_text, 'WAX-26-01')
        self.assertEqual(lines['Quantity'].value_number, 4)
        self.assertEqual(lines['Production Date'].value_date, fields.Date.context_today(checklist))
        self.assertEqual(lines['Lot'].value_reference, production.lot_producing_ids)
        self.assertTrue(lines['Finish OK?'].value_boolean)
        self.assertEqual(lines['Comments'].value_text_area, 'Smooth finish')
        # The lot, order and product show their QA checks.
        self.assertEqual(production.qa_checklist_count, 1)
        self.assertEqual(production.lot_producing_ids.qa_checklist_count, 1)
        self.assertEqual(self.lot_product.product_tmpl_id.qa_checklist_count, 1)
        # The work order shows it on the app.
        self.assertEqual(workorder._terminal_payload()['qa'][0]['id'], checklist.id)

    def test_lot_linked_when_set_later(self):
        production = self._production(product=self.lot_product, qty=1)
        workorder = production.workorder_ids
        self._event('qa', workorder, template_id=self.template.id, state='draft', answers={})
        checklist = production.qa_checklist_ids
        self.assertFalse(checklist.mrp_lot_ids)
        self.assertEqual(checklist.state, 'draft')
        self._event('finish', workorder, lot='WAX-LATE')
        self.assertEqual(production.state, 'done')
        self.assertEqual(checklist.mrp_lot_ids.name, 'WAX-LATE')

    def test_template_outside_groups_refused(self):
        production = self._production()
        result = self._event('qa', production.workorder_ids, template_id=self.other_template.id, answers={})
        self.assertEqual(result['status'], 'error')
        self.assertFalse(self.env['checklist.checklist'].search([('production_id', '=', production.id)]))

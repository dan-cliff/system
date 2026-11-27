# -*- coding: utf-8 -*-
from odoo import Command, api, fields, models

from .checklist import prefill_key

LAYOUT_FIELDS = {'section_break': 'layout_title_position'}


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    def _terminal_qa_templates(self):
        self.ensure_one()
        groups = self._terminal_company().mrp_qa_checklist_group_ids
        if not groups:
            return self.env['checklist.template']
        return self.env['checklist.template'].sudo().search([('group_ids', 'in', groups.ids)])

    def _terminal_qa_payload(self, template):
        questions = []
        for question in template.question_ids.filtered('active'):
            questions.append({
                'id': question.id,
                'name': question.name,
                'description': question.description or '',
                'type': question.question_type,
                'options': [{'id': option.id, 'name': option.name, 'color': option.color or ''}
                            for option in question.option_ids.filtered('active')],
                'prefill': prefill_key(question),
                'instructions': question.instructions or '',
                'title_position': question.layout_title_position or 'above',
                'conditional': question.conditional,
                'condition_logic': question.condition_logic,
                'condition_rules': question.condition_ids._rule_vals() if question.conditional else [],
                # Filters on the user or checklist can't be checked on the device:
                # those questions show, and Odoo applies the filters to the checklist.
                'condition_context': {},
            })
        return {'id': template.id, 'name': template.name, 'questions': questions}

    def _terminal_config(self):
        config = super()._terminal_config()
        templates = self._terminal_qa_templates()
        if templates:
            config['features']['qa'] = {'templates': [self._terminal_qa_payload(t) for t in templates]}
        return config

    @api.model
    def _terminal_actions(self):
        return dict(super()._terminal_actions(), qa='_terminal_qa')


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def _terminal_payload(self):
        payload = super()._terminal_payload()
        checklists = self.env['checklist.checklist'].sudo().search(
            [('production_id', '=', self.production_id.id)], order='id')
        payload['qa'] = [{
            'id': checklist.id,
            'name': checklist.name,
            'template': checklist.template_id.name,
            'state': checklist.state,
        } for checklist in checklists]
        return payload

    def _terminal_qa(self, employee, when, event):
        self.ensure_one()
        checklist = self.env['checklist.checklist']._mrp_create_from_terminal(self, employee, when, event)
        return self.env._('QA checklist %(name)s (%(template)s) saved.',
                          name=checklist.name, template=checklist.template_id.name)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    qa_checklist_ids = fields.One2many('checklist.checklist', 'production_id', string='QA Checks')
    qa_checklist_count = fields.Integer(compute='_compute_qa_checklist_count', string='QA Checks')

    def _compute_qa_checklist_count(self):
        counts = dict(self.env['checklist.checklist'].sudo()._read_group(
            [('production_id', 'in', self.ids)], ['production_id'], ['__count']))
        for production in self:
            production.qa_checklist_count = counts.get(production, 0)

    def _qa_link_lots(self):
        """QA checks link to the lot / serial numbers the order produces, also
        when those are set after the check was done."""
        for production in self.sudo():
            lots = production.lot_producing_ids
            if not lots:
                continue
            for checklist in self.env['checklist.checklist'].sudo().search([('production_id', '=', production.id)]):
                missing = lots - checklist.mrp_lot_ids
                if missing:
                    checklist.mrp_lot_ids = [Command.link(lot.id) for lot in missing]

    def write(self, vals):
        result = super().write(vals)
        if 'lot_producing_ids' in vals:
            self._qa_link_lots()
        return result

    def button_mark_done(self):
        result = super().button_mark_done()
        self._qa_link_lots()
        return result

    def action_view_qa_checklists(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('checklists.action_checklist')
        action.update({
            'name': self.env._('QA Checks'),
            'domain': [('production_id', '=', self.id)],
            'context': {'default_production_id': self.id, 'default_mrp_product_id': self.product_id.id},
        })
        return action


class StockLot(models.Model):
    _inherit = 'stock.lot'

    qa_checklist_ids = fields.Many2many(
        'checklist.checklist', 'checklist_checklist_mrp_lot_rel', 'lot_id', 'checklist_id', string='QA Checks',
    )
    qa_checklist_count = fields.Integer(compute='_compute_qa_checklist_count', string='QA Checks')

    def _compute_qa_checklist_count(self):
        Checklist = self.env['checklist.checklist'].sudo()
        for lot in self:
            lot.qa_checklist_count = Checklist.search_count([('mrp_lot_ids', 'in', lot.ids)]) if lot.id else 0

    def action_view_qa_checklists(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('checklists.action_checklist')
        action.update({
            'name': self.env._('QA Checks'),
            'domain': [('mrp_lot_ids', 'in', self.ids)],
            'context': {'default_mrp_product_id': self.product_id.id, 'default_mrp_lot_ids': self.ids},
        })
        return action


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    qa_checklist_count = fields.Integer(compute='_compute_qa_checklist_count', string='QA Checks')

    def _compute_qa_checklist_count(self):
        counts = dict(self.env['checklist.checklist'].sudo()._read_group(
            [('mrp_product_id.product_tmpl_id', 'in', self.ids)], ['mrp_product_id'], ['__count']))
        for template in self:
            template.qa_checklist_count = sum(
                count for product, count in counts.items() if product.product_tmpl_id == template)

    def action_view_qa_checklists(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('checklists.action_checklist')
        action.update({
            'name': self.env._('QA Checks'),
            'domain': [('mrp_product_id.product_tmpl_id', '=', self.id)],
            'context': {'default_mrp_product_id': self.product_variant_id.id},
        })
        return action

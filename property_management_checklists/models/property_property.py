# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PropertyProperty(models.Model):
    _inherit = 'property.property'

    checklist_ids = fields.One2many('checklist.checklist', 'property_id', string='Checklists')
    checklist_count = fields.Integer(compute='_compute_checklist_count')
    property_checklist_enabled = fields.Boolean(compute='_compute_property_checklist_enabled')

    @api.depends('checklist_ids')
    def _compute_checklist_count(self):
        counts = dict(self.env['checklist.checklist']._read_group(
            [('property_id', 'in', self.ids)], ['property_id'], ['__count']))
        for prop in self:
            prop.checklist_count = counts.get(prop, 0)

    @api.depends('company_id')
    def _compute_property_checklist_enabled(self):
        for prop in self:
            prop.property_checklist_enabled = bool(
                (prop.company_id or self.env.company)._property_checklist_groups())

    def action_view_checklists(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('checklists.action_checklist')
        action.update({
            'name': self.env._('Checklists: %s', self.name),
            'domain': [('property_id', '=', self.id)],
            'context': {
                'default_property_id': self.id,
                'default_company_id': self.company_id.id,
            },
        })
        return action

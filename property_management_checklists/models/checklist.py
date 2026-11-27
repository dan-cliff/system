# -*- coding: utf-8 -*-
from odoo import api, fields, models


class Checklist(models.Model):
    _inherit = 'checklist.checklist'

    property_id = fields.Many2one(
        'property.property', string='Property', tracking=True, ondelete='set null', index='btree_not_null',
        help='The property this checklist is for.',
    )
    property_visible = fields.Boolean(
        compute='_compute_property_visible',
        help="The checklist's template is in a Checklist Group linked to Property (Settings › Property).",
    )

    @api.depends('template_id.group_ids', 'company_id')
    @api.depends_context('company')
    def _compute_property_visible(self):
        for checklist in self:
            company = checklist.company_id._origin or self.env.company
            groups = checklist.template_id._origin.group_ids
            checklist.property_visible = bool(groups & company._property_checklist_groups())

    @api.onchange('template_id')
    def _onchange_template_id_property(self):
        if self.property_id and not self.property_visible:
            self.property_id = False

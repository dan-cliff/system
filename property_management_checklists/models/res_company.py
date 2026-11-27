# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    property_checklist_enabled = fields.Boolean(string='Integrate Checklists with Property')
    property_checklist_group_ids = fields.Many2many(
        'checklist.group', 'res_company_property_checklist_group_rel', 'company_id', 'group_id',
        string='Property Checklist Groups',
        help='Checklists from templates in these Checklist Groups can be linked to a property.',
    )

    def _property_checklist_groups(self):
        """The Checklist Groups linked to Property (none unless integrated)."""
        self.ensure_one()
        if not self.property_checklist_enabled:
            return self.env['checklist.group']
        return self.sudo().property_checklist_group_ids.sudo(False)

# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    talent_checklist_enabled = fields.Boolean(related='company_id.talent_checklist_enabled', readonly=False)
    talent_checklist_group_ids = fields.Many2many(related='company_id.talent_checklist_group_ids', readonly=False)

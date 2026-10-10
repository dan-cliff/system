# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    checklist_default_template_id = fields.Many2one(
        'checklist.template', string='Default Checklist Template',
        config_parameter='checklists.default_template_id',
        help='Template new Checklists start from.',
    )

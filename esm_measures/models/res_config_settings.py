# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    esm_fak_default_template_id = fields.Many2one(
        'esm.fak.template', string='Default Template',
        config_parameter='esm_measures.fak_default_template_id',
        help='Template new First Aid Kit Inspections start from.',
    )

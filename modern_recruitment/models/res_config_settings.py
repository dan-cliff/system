# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Ticking one installs its job board app (Odoo installs module_* fields on save).
    module_modern_recruitment_linkedin = fields.Boolean(string='LinkedIn')
    module_modern_recruitment_seek = fields.Boolean(string='SEEK')
    module_modern_recruitment_jora = fields.Boolean(string='Jora')

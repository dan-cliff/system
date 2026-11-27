# -*- coding: utf-8 -*-
from odoo import fields, models

AUTO_PRODUCTION_PARAM = 'laser_jobbing_manufacturing.auto_production'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    laser_auto_production = fields.Boolean(
        string='Manufacturing Orders for Laser Jobs',
        help='Confirming a laser job whose product has a bill of materials creates and confirms a '
             'manufacturing order for it, unless the order it comes from already made one.',
    )

    def get_values(self):
        res = super().get_values()
        value = self.env['ir.config_parameter'].sudo().get_param(AUTO_PRODUCTION_PARAM, 'True')
        res['laser_auto_production'] = value in ('True', 'true', '1')
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            AUTO_PRODUCTION_PARAM, 'True' if self.laser_auto_production else 'False')

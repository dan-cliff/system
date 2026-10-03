from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    cd_default_color_1 = fields.Char(string='Default Colour 1', config_parameter='custom_dashboard.default_color_1')
    cd_default_color_2 = fields.Char(string='Default Colour 2', config_parameter='custom_dashboard.default_color_2')
    cd_default_color_3 = fields.Char(string='Default Colour 3', config_parameter='custom_dashboard.default_color_3')
    cd_default_color_4 = fields.Char(string='Default Colour 4', config_parameter='custom_dashboard.default_color_4')
    cd_default_color_5 = fields.Char(string='Default Colour 5', config_parameter='custom_dashboard.default_color_5')
    cd_default_color_6 = fields.Char(string='Default Colour 6', config_parameter='custom_dashboard.default_color_6')

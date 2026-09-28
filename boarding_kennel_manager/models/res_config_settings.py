from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kennel_observation_times = fields.Char(related='company_id.kennel_observation_times', readonly=False)

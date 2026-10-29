from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    onsite_systray = fields.Boolean(related='company_id.onsite_systray', readonly=False)
    onsite_location_tracking = fields.Boolean(related='company_id.onsite_location_tracking', readonly=False)
    onsite_auto_sign_out = fields.Boolean(related='company_id.onsite_auto_sign_out', readonly=False)
    onsite_auto_sign_out_hours = fields.Float(related='company_id.onsite_auto_sign_out_hours', readonly=False)

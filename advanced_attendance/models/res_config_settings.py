from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    onsite_systray = fields.Boolean(related='company_id.onsite_systray', readonly=False)
    onsite_location_tracking = fields.Boolean(related='company_id.onsite_location_tracking', readonly=False)
    onsite_auto_sign_out = fields.Boolean(related='company_id.onsite_auto_sign_out', readonly=False)
    onsite_auto_sign_out_hours = fields.Float(related='company_id.onsite_auto_sign_out_hours', readonly=False)
    onsite_overtime_validation = fields.Selection(related='company_id.onsite_overtime_validation', readonly=False)
    onsite_absence_management = fields.Boolean(related='company_id.onsite_absence_management', readonly=False)
    onsite_display_overtime = fields.Boolean(related='company_id.onsite_display_overtime', readonly=False)

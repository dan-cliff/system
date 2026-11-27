# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    property_reminder_days = fields.Integer(related='company_id.property_reminder_days', readonly=False)

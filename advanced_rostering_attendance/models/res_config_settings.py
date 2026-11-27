# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rostering_late_grace_minutes = fields.Integer(
        string='Late After (minutes)', default=5, config_parameter='advanced_rostering.late_grace_minutes',
        help='A sign in more than this many minutes after the start of the shift counts as late.',
    )

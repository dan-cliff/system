# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    personnel_badge_count = fields.Integer(string='ID Badges', compute='_compute_personnel_badge_count')

    def _compute_personnel_badge_count(self):
        count = self.env['advanced.hr.badge.template'].search_count([])
        for settings in self:
            settings.personnel_badge_count = count

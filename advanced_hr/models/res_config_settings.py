# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    personnel_badge_count = fields.Integer(string='ID Badges', compute='_compute_personnel_badge_count')

    def _compute_personnel_badge_count(self):
        # Settings is opened by administrators who may have no Personnel
        # permission: only a count is shown, so count as superuser.
        count = self.env['advanced.hr.badge.template'].sudo().search_count([])
        for settings in self:
            settings.personnel_badge_count = count

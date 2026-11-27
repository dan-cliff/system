# -*- coding: utf-8 -*-
from odoo import api, models


class RosteringPublicHoliday(models.Model):
    _inherit = 'rostering.public.holiday'

    @api.model
    def _after_import(self):
        super()._after_import()
        # New Country / State jurisdictions: add them to the employees living there.
        self.env['hr.employee']._rostering_apply_address_jurisdictions()

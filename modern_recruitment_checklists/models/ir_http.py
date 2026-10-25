# -*- coding: utf-8 -*-
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        info = super().session_info()
        if self.env.user._is_internal():
            # Shows Send Questionnaire in applicants' chatter.
            info['talent_questionnaires'] = bool(self.env.company.talent_checklist_enabled)
        return info

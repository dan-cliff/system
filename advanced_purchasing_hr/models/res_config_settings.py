# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    purchasing_escalate_delegation = fields.Boolean(
        related='company_id.purchasing_escalate_delegation', readonly=False)

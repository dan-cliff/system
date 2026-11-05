# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    mrp_scanner_require_components = fields.Boolean(
        string='Scan Every Component',
        help='On the Scanner, every component must be scanned (or its quantity typed) before the '
             'manufacturing order can be produced.',
    )
    mrp_scanner_ready_only = fields.Boolean(
        string='Only Orders Ready to Produce', default=True,
        help='The Scanner lists only manufacturing orders whose components are available (and those '
             'already in progress). Turn off to list orders still waiting for components too.',
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mrp_scanner_require_components = fields.Boolean(
        related='company_id.mrp_scanner_require_components', readonly=False)
    mrp_scanner_ready_only = fields.Boolean(related='company_id.mrp_scanner_ready_only', readonly=False)

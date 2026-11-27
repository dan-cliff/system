# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    purchasing_escalate_delegation = fields.Boolean(
        'Escalate Approvals', default=True,
        help="Skip Up Managers whose own spend delegation is below the order total, so the order goes "
             "to the first manager above them who can spend that much.")

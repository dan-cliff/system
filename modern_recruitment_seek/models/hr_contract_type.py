# -*- coding: utf-8 -*-
from odoo import fields, models

# SEEK's work type codes, so a fixed technical selection.
SEEK_WORK_TYPES = [
    ('FullTime', 'Full time'),
    ('PartTime', 'Part time'),
    ('ContractTemp', 'Contract / Temp'),
    ('CasualVacation', 'Casual / Vacation'),
]


class HrContractType(models.Model):
    _inherit = 'hr.contract.type'

    seek_work_type = fields.Selection(
        SEEK_WORK_TYPES, string='SEEK Work Type',
        help='The work type SEEK ads use for job positions of this Employment Type.',
    )

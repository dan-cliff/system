# -*- coding: utf-8 -*-
from odoo import fields, models

# Jora's job types, so a fixed technical selection.
JORA_JOB_TYPES = [
    ('Full time', 'Full time'),
    ('Part time', 'Part time'),
    ('Contract', 'Contract'),
    ('Temporary', 'Temporary'),
    ('Casual', 'Casual'),
    ('Internship', 'Internship'),
]


class HrContractType(models.Model):
    _inherit = 'hr.contract.type'

    jora_job_type = fields.Selection(
        JORA_JOB_TYPES, string='Jora Job Type',
        help='The job type Jora shows for job positions of this Employment Type.',
    )

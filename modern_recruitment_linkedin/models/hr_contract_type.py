# -*- coding: utf-8 -*-
from odoo import fields, models

# LinkedIn's job feed codes, so a fixed technical selection.
LINKEDIN_JOB_TYPES = [
    ('FULL_TIME', 'Full-time'),
    ('PART_TIME', 'Part-time'),
    ('CONTRACT', 'Contract'),
    ('TEMPORARY', 'Temporary'),
    ('VOLUNTEER', 'Volunteer'),
    ('INTERNSHIP', 'Internship'),
    ('OTHER', 'Other'),
]


class HrContractType(models.Model):
    _inherit = 'hr.contract.type'

    linkedin_job_type = fields.Selection(
        LINKEDIN_JOB_TYPES, string='LinkedIn Job Type',
        help='The job type LinkedIn shows for job positions of this Employment Type.',
    )

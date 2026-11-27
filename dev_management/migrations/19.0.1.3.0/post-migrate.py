"""Sprints are now named Sprint YYYY-NNN, numbered within each year.

The sequence is noupdate data, so an existing database keeps the old
"Sprint N" sequence: switch it to the yearly one. Existing sprints keep
their names.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    sequence = env.ref('dev_management.seq_dev_sprint', raise_if_not_found=False)
    if sequence:
        sequence.write({'prefix': 'Sprint %(range_year)s-', 'padding': 3, 'use_date_range': True})

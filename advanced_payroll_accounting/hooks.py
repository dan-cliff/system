# -*- coding: utf-8 -*-


def post_init_hook(env):
    """A Payroll journal for every company that has a chart of accounts."""
    for company in env['res.company'].search([]):
        company._payroll_ensure_journal()

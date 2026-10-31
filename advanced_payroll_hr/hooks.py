# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Employees and payroll profiles made before Personnel was switched on:
    take their Payroll Country from the Work Address."""
    employees = env['hr.employee'].with_context(active_test=False).search([])
    employees._compute_payroll_country_id()
    profiles = env['payroll.employee'].with_context(active_test=False).search([])
    profiles._compute_country_id()

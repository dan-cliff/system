# -*- coding: utf-8 -*-

PARAM = 'advanced_payroll.hours_source'


def post_init_hook(env):
    """Switching the feature on pays hourly employees from their timesheets."""
    env['ir.config_parameter'].sudo().set_param(PARAM, 'timesheet')


def uninstall_hook(env):
    params = env['ir.config_parameter'].sudo()
    if params.get_param(PARAM) == 'timesheet':
        params.set_param(PARAM, 'standard')

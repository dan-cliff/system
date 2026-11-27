# -*- coding: utf-8 -*-

PARAM = 'advanced_payroll.hours_source'


def uninstall_hook(env):
    params = env['ir.config_parameter'].sudo()
    if params.get_param(PARAM) == 'roster':
        params.set_param(PARAM, 'standard')

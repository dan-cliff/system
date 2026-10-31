# -*- coding: utf-8 -*-
from .models.res_config_settings import COUNTRY_MODULES


def post_init_hook(env):
    """Like Accounting's fiscal localisations: install the Payroll app of
    each company's country, and switch on the Accounting integration."""
    countries = set(env['res.company'].search([]).mapped('country_id.code'))
    names = [module for code, module in COUNTRY_MODULES.items() if code in countries]
    names.append('advanced_payroll_accounting')
    modules = env['ir.module.module'].search([('name', 'in', names), ('state', '=', 'uninstalled')])
    if modules:
        modules.button_install()

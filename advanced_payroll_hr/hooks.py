# -*- coding: utf-8 -*-


def _set_employees_menu(env, action_xmlid):
    menu = env.ref('advanced_payroll.menu_payroll_employees', raise_if_not_found=False)
    action = env.ref(action_xmlid, raise_if_not_found=False)
    if menu and action:
        menu.action = f'{action._name},{action.id}'


def post_init_hook(env):
    """Employees and payroll details made before Personnel was switched on:
    take their Payroll Country from the Work Address."""
    employees = env['hr.employee'].with_context(active_test=False).search([])
    employees._compute_payroll_country_id()
    profiles = env['payroll.employee'].with_context(active_test=False).search([])
    profiles._compute_country_id()


def uninstall_hook(env):
    """Payroll › Employees opens Payroll's own Payroll Employees again (this
    module pointed it at Personnel employees: views/payroll_menus.xml)."""
    _set_employees_menu(env, 'advanced_payroll.action_payroll_employee')

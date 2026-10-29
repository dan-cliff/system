# -*- coding: utf-8 -*-

# Employees' own menus that Personnel replaces with its own (data/personnel_titles.xml
# hides them); they come back when Personnel is uninstalled.
REPLACED_HR_MENUS = (
    'hr.menu_hr_employee_payroll',
    'hr.menu_hr_employee',
    'hr.menu_hr_department_kanban',
)


def post_init_hook(env):
    # Employees created before Personnel have no Audit Trail; nothing to do,
    # but make sure every badge has its print action.
    env['advanced.hr.badge.template'].with_context(active_test=False).search([])._sync_report_action()


def uninstall_hook(env):
    """Give the Employees app back its name, menus and badge."""
    root = env.ref('hr.menu_hr_root', raise_if_not_found=False)
    if root:
        root.write({'name': 'Employees', 'web_icon': 'hr,static/description/icon.png'})
    for xmlid in REPLACED_HR_MENUS:
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu:
            menu.active = True
    tags = env.ref('hr.menu_view_employee_category_form', raise_if_not_found=False)
    no_one = env.ref('base.group_no_one', raise_if_not_found=False)
    if tags and no_one:
        tags.group_ids = [(6, 0, no_one.ids)]
    job_menu = env.ref('hr.menu_view_hr_job', raise_if_not_found=False)
    job_action = env.ref('hr.action_hr_job', raise_if_not_found=False)
    if job_menu and job_action:
        job_menu.action = job_action
    badge = env.ref('hr.hr_employee_print_badge', raise_if_not_found=False)
    if badge:
        badge.write({
            'binding_model_id': env['ir.model']._get('hr.employee').id,
            'binding_type': 'report',
        })
    env['ir.actions.report'].search([('report_name', '=', 'advanced_hr.report_badge')]).unlink()
    env['report.paperformat'].search([('name', '=like', 'ID Badge: %')]).unlink()

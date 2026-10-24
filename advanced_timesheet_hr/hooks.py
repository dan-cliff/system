# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Timesheets made before Employees was installed: link them to their user's employee."""
    sheets = env['advanced.timesheet'].with_context(active_test=False).search([('employee_id', '=', False)])
    for sheet in sheets:
        employee = sheet.user_id.with_company(sheet.company_id).employee_id
        if employee:
            sheet.employee_id = employee

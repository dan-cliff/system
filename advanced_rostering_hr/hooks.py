# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Shifts, template shifts and leave made before Personnel was switched
    on: link them to their user's employee."""
    for model in ('rostering.shift', 'rostering.template.line', 'rostering.leave'):
        records = env[model].with_context(active_test=False).search([
            ('employee_id', '=', False), ('user_id', '!=', False),
        ])
        for record in records:
            employee = record.user_id.with_company(record.company_id or env.company).employee_id
            if employee:
                record.employee_id = employee

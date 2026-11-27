# -*- coding: utf-8 -*-
{
    'name': 'Personnel',
    'version': '19.0.1.0.1',
    'category': 'Human Resources/Employees',
    'sequence': 95,
    'summary': 'A modern Employees app: people, departments, ID badges and an audit trail',
    'description': """
Personnel (advanced_hr)
=======================
A more modern version of Odoo's Employees app, built on Odoo's own models
(hr.employee, hr.version, hr.department, hr.job, ...), so everything that
works with Employees keeps working. Personnel takes the Employees app's
place on the home screen.

* Everything Employees does: employee profiles with work, resume, personal,
  payroll and settings tabs, versions (contract history), departures,
  onboarding / offboarding plans, users, bank accounts, departments, the
  directory, job positions, work locations, working schedules, contract
  templates and the Employees settings.
* Permissions per CLAUDE.md: per-model privileges on Employees and
  Departments (Create Only, Create and Edit Own / My Team / All, View All,
  Delete Own / All), an Audit Trail privilege and the Personnel
  Administrator. Standard roles ship in advanced_hr_permission.
  Every Employees permission includes Odoo's HR Officer group (Odoo needs it
  to manage employees); the record rules decide which employees, private
  details and bank accounts included. Colleagues outside a user's
  permissions still show their public profile, as in Odoo.
* Audit Trail instead of chatter tracking: every save of an employee or a
  department records one Audit Trail entry with who, when and the original
  and new value of each changed field.
* ID Badges: design badge layouts in a visual editor (page size, text with
  employee fields, formatting, company logo and colours, photos, QR codes
  and barcodes for any field). A badge with a company is only offered to
  that company's employees; without one it is offered to everyone. Each
  badge is listed on the employee's Print menu.
* Every employee needs a Work Address (Work Information tab).
* Lists start with the ID, dates show as dd/mm/yyyy, a Reports menu for
  Report Builder sits before Configuration.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['hr', 'mail'],
    'data': [
        'security/advanced_hr_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/personnel_titles.xml',
        'report/badge_report.xml',
        'views/hr_employee_views.xml',
        'views/hr_department_views.xml',
        'views/hr_employee_public_views.xml',
        'views/config_list_views.xml',
        'views/audit_trail_views.xml',
        'views/badge_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
        'data/badge_template_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_hr/static/src/scss/personnel.scss',
            'advanced_hr/static/src/badge_designer/**/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': True,
}

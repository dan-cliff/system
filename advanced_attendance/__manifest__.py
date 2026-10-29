{
    'name': 'On Site',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'sequence': 205,
    'summary': 'Attendances, sign in kiosks with rules and questionnaires, offline PWA kiosks '
               'and sign in / out alerts',
    'description': """
On Site (advanced_attendance)
=============================
A new version of the Attendances app that replaces Odoo's Attendances
(hr_attendance) and our Attendance Kiosks add-on, so both can be uninstalled.

* Attendances: who signed in and out, when and where, worked hours (less the
  lunch break of the working schedule), no overlapping attendances, an
  "On Site Now" board, analysis (pivot / graph) and employees shown as
  present while signed in.
* Sign in from Odoo: a Sign In / Out button in the top toolbar (also on the
  home screen), optionally recording GPS position, IP address and browser.
* Automatic sign out for people who forget, per kiosk or for the company.
* Kiosks: as many as you need, each with its own URL that installs as a
  Progressive Web App and keeps working offline; badge or name + PIN; a rule
  builder for who may sign in; minimum Learning capabilities per kiosk and
  per rule with expiry warnings; per-kiosk handling of signing in or out at
  another kiosk.
* Questionnaires on sign in (every time, first of the day, first of the day
  at the location, first ever at the location) whose answers can refuse the
  sign in; answers are kept against the attendance.
* Sign in / out alerts: Discuss messages when particular employees (or
  everyone) arrive or leave, limited to sites, dates, days and times.
* Permissions per CLAUDE.md (Attendances, Kiosks and Alerts privileges, Sign
  In from Odoo and the On Site Administrator); roles ship in
  advanced_attendance_permission.

On install, existing attendances, kiosks, questionnaires, responses and
alerts from Attendances / Attendance Kiosks are copied across. Kiosks get
new URLs (/onsite/...), so set kiosk devices up again with them.
""",
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_hr', 'learning_management', 'mail'],
    'data': [
        'security/advanced_attendance_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/ir_cron_data.xml',
        'data/questionnaire_data.xml',
        'views/advanced_attendance_views.xml',
        'views/attendance_kiosk_rule_views.xml',
        'views/attendance_kiosk_questionnaire_views.xml',
        'views/attendance_kiosk_response_views.xml',
        'views/attendance_kiosk_views.xml',
        'views/attendance_alert_views.xml',
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
        'views/attendance_kiosk_templates.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_attendance/static/src/systray/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}

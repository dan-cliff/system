# -*- coding: utf-8 -*-
{
    'name': 'Rostering',
    'version': '19.0.1.0.1',
    'category': 'Human Resources/Rostering',
    'sequence': 96,
    'summary': 'Rosters built from duties, standard shifts and templates, plus leave requests',
    'description': """
Rostering (advanced_rostering)
==============================
Planning and Time Off in one app.

* Rosters: one roster per period. Settings › Rostering chooses whether rosters
  are published Weekly, Fortnightly, Monthly or Quarterly (and the date
  weekly / fortnightly periods count from). Draft rosters are built shift by
  shift or from a Roster Template, then published to the people on them and
  unpublished again for changes.
* Shifts: a person, a day, a Standard Shift (start, end and breaks), a Duty,
  and the paid hours less unpaid breaks. Shifts that clash with approved leave
  are flagged.
* Libraries (Configuration): Duties, Standard Shifts (start time, end time and
  paid / unpaid breaks), Roster Templates (a standard roster for the cycle in
  Settings, applied to a draft roster in one click) and Leave Types.
* My Roster and Leave: the logged-in user's published roster, their upcoming
  leave and a Request Leave button.
* Leave Requests: everyone can request their own leave; managers (Create and
  Edit My Team) and above can request it for others. Without Personnel the
  submitted requests wait in the To Approve queue for the Leave Requests:
  Approve team; with Personnel they go to the employee's Manager.
* Feature switches (Settings › Rostering, each shown only when that app is
  installed):
  - Personnel (advanced_rostering_hr): people are Personnel employees, the
    Manager is shown, managers approve leave and see My Team's Rosters.
  - On Site (advanced_rostering_attendance): rostered shifts compared with
    attendances (attended, late, absent).
  - Advanced Timesheets (advanced_rostering_timesheet): fill timesheets from
    the roster and approved leave.
* Permissions per CLAUDE.md; standard roles ship in
  advanced_rostering_permission.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['base', 'base_setup', 'mail'],
    'data': [
        'security/advanced_rostering_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/rostering_data.xml',
        'views/rostering_duty_views.xml',
        'views/rostering_standard_shift_views.xml',
        'views/rostering_template_views.xml',
        'views/rostering_shift_views.xml',
        'views/rostering_roster_views.xml',
        'views/rostering_leave_type_views.xml',
        'views/rostering_leave_views.xml',
        'wizard/rostering_apply_template_wizard_views.xml',
        'wizard/rostering_leave_refuse_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/rostering_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_rostering/static/src/my_roster/*',
        ],
    },
    'installable': True,
    'application': True,
}

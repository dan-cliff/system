{
    'name': 'Attendance Kiosks',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Multiple sign in kiosks with their own URL, sign in rules, '
               'Learning capability checks, auto sign out, questionnaires and offline PWA support',
    'description': """
Attendance Kiosks
=================
* Create as many kiosks as you need. Each kiosk belongs to a Company and a
  Work Location and has its own unique URL that can be installed as a
  Progressive Web App (PWA) and keeps working offline.
* Rule builder for who may sign in at each kiosk: a base filter on
  employees, plus any number of conditional rules ("employees matching X
  must also match Y / hold these capabilities"), or rules that refuse
  sign in outright.
* Minimum current capabilities from the Learning module (completed,
  unexpired licences, qualifications and training) per kiosk and per rule,
  with an optional warning when a capability is about to expire.
* Automatic sign out per kiosk, after a number of hours or at a time of
  day, and per-kiosk control of what happens when a worker signs in or out
  at a different kiosk while signed in here.
* Questionnaires that pop up on sign in, every time, on the first sign in
  of the day, on the first sign in of the day at the location, or on the
  first ever sign in at the location. Answers can refuse the sign in and
  are kept against the attendance.
* Offline mode: the kiosk keeps a copy of who may sign in and records
  sign ins, sign outs and questionnaire answers locally, then syncs them
  when the connection returns.
""",
    'author': "Cliff's Country Crafts",
    'depends': ['hr_attendance', 'learning_management'],
    'data': [
        'security/attendance_kiosk_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'data/attendance_kiosk_questionnaire_data.xml',
        'views/attendance_kiosk_rule_views.xml',
        'views/attendance_kiosk_questionnaire_views.xml',
        'views/attendance_kiosk_response_views.xml',
        'views/attendance_kiosk_views.xml',
        'views/hr_attendance_views.xml',
        'views/attendance_kiosk_menus.xml',
        'views/attendance_kiosk_templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

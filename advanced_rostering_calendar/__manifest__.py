# -*- coding: utf-8 -*-
{
    'name': 'Rostering - Calendar',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Rostering',
    'summary': 'Leave requests in the Calendar app, with a shared Leave Requests calendar',
    'description': """
        Installs automatically when both Rostering and Calendar are installed.

        - Every leave request (draft, waiting for approval or approved) is an
          event in the person's calendar, named with the leave type and its
          status ("Annual Leave (To Approve)"): a whole-day event for whole
          days, the From and To times for a part day
        - The event follows the request: changing the dates, type, person or
          status updates it; refusing, cancelling or deleting the request
          removes it. The event itself is read-only in Calendar (change the
          request in Rostering) and sends no invitations
        - Leave Requests calendar: a shared calendar in the Calendar app's
          sidebar holding every leave request. Each user only sees the leave
          events of the requests they can see in Rostering
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_rostering', 'calendar'],
    'data': [
        'data/rostering_calendar_data.xml',
        'security/rostering_calendar_security.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

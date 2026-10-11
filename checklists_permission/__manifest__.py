# -*- coding: utf-8 -*-
{
    'name': 'Checklists - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'A Permission Management Role for each Checklist Group permission',
    'description': """
        Installs automatically when both Checklists and Permission Management
        are installed.

        Every Checklist Group gets one Role per permission, named after the
        group (e.g. "Checklists – Vehicles: Template Authoring"):

        - Template Authoring
        - Template Delete
        - Record Create and Edit Own
        - Record Create and Edit All
        - Record View All
        - Record Delete Own
        - Record Delete All

        The Roles are added, renamed and removed with their Checklist Group.
    """,
    'author': 'Custom',
    'depends': ['checklists', 'permission_management'],
    'data': [
        'data/checklist_permission_role_sync.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

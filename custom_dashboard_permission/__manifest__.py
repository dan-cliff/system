{
    'name': 'Custom Dashboards - Permission Profiles',
    'version': '19.0.1.0.0',
    'summary': 'Choose which dashboards each Permission Profile can open',
    'description': """
Custom Dashboards - Permission Profiles
=======================================
Installed automatically with Custom Dashboards and Permission Management.

* Adds a Dashboards list to every Permission Profile. Users on that profile
  can open those dashboards (alongside dashboards shared with them directly
  or through a group).
* Shows the profiles on each dashboard's Sharing section.
* Users whose profile lists dashboards get Dashboards "User" access
  automatically, and lose it again when the profile no longer grants it.
""",
    'category': 'Productivity',
    'author': "Cliff's Country Crafts",
    'website': 'https://aberbran.farm',
    'depends': ['custom_dashboard', 'permission_management'],
    'data': [
        'security/security.xml',
        'views/permission_profile_views.xml',
        'views/dashboard_views.xml',
    ],
    'installable': True,
    'auto_install': True,
    'license': 'LGPL-3',
}

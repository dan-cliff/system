{
    'name': 'Organisation Structure',
    'version': '19.0.1.2.0',
    'category': 'Administration',
    'summary': 'Divisions, Business Units, Locations and Departments with per-user record scoping',
    'description': """
Company-aware organisational hierarchy:

    Company > Division > Business Unit > Location > Department

Each level inherits its company and higher-level parents from its direct
parent. Users get a Home Division / Business Unit / Location / Department,
can be scoped across all apps to one of those levels, and can have
app-specific scoping to any combination of org units.

Every primary model of every installed app (opened from the app's menus
outside Configuration / Settings) automatically gets Division, Business
Unit, Location and Department fields, an Organisation section on its form,
and record scoping. Records created from a parent record copy the parent's
Organisation. Other models can inherit ``org.scope.mixin``.
""",
    'author': "Cliff's Country Crafts",
    'depends': ['base'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'views/org_actions.xml',
        'views/org_division_views.xml',
        'views/org_business_unit_views.xml',
        'views/org_location_views.xml',
        'views/org_department_views.xml',
        'views/res_users_views.xml',
        'views/menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}

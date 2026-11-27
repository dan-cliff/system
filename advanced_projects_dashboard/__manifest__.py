{
    'name': 'Project - Dashboards',
    'version': '19.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Open Custom Dashboards from a project, filtered to that project',
    'description': """
        Installs automatically when both Project (advanced_projects) and Custom
        Dashboards are installed.

        - Dashboards can be made available in every project ("Available in
          Projects" on the dashboard) or picked per project (the project's
          Dashboards tab); a project's Dashboards smart button opens them
        - Each widget's filter has a Project Field: the field on the widget's
          records that holds the project (e.g. Project, or Project Task ›
          Project). It is filled in automatically when the model has one
        - Opened from a project, every widget with a Project Field only shows
          that project's records; opened from the Dashboards app, nothing is
          filtered by project
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_projects', 'custom_dashboard'],
    'data': [
        'views/custom_dashboard_views.xml',
        'views/advanced_project_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_projects_dashboard/static/src/*',
        ],
    },
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

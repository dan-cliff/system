{
    'name': 'Custom Dashboards - Website',
    'version': '19.0.1.0.0',
    'summary': 'Publish custom dashboards as public pages on the website',
    'description': """
Publish dashboards built with Custom Dashboards as read-only pages on the
website, at /dashboards/<name>.

* Publish or unpublish each dashboard from its form (Website tab).
* Choose which user's access rights the public page reads data as.
* Optionally limit a dashboard to one website and add it to the website menu.
* A /dashboards page lists every published dashboard, and published
  dashboards are added to the sitemap.
""",
    'category': 'Website',
    'author': "Cliff's Country Crafts",
    'website': 'https://aberbran.farm',
    'depends': ['custom_dashboard', 'website'],
    'data': [
        'views/custom_dashboard_views.xml',
        'views/website_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'custom_dashboard/static/src/chart_config.js',
            'custom_dashboard/static/src/widget_card.js',
            'custom_dashboard/static/src/widget_card.xml',
            'custom_dashboard/static/src/widget_card.scss',
            'custom_dashboard_website/static/src/**/*',
        ],
    },
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

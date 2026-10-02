{
    'name': 'Custom Dashboards',
    'version': '19.0.1.0.0',
    'summary': 'Build drag-and-drop dashboards of charts, KPIs and tables from any model',
    'description': """
Custom Dashboards
=================
A visual dashboard builder powered by gridstack.js and Chart.js.

* Drag widgets from a palette onto a 12-column grid, then move and resize them.
* Charts: column, bar (plain, stacked and 100%), line, area, combo, pie,
  donut, polar area, radar, scatter, bubble, waterfall, funnel and gauge.
* KPI cards with targets, plus grouped tables, pivot tables, text and images.
* Every widget reads live, aggregated data from any Odoo model (group by,
  date interval, series split, measure and filter). Users only see the
  data their access rights allow.
* Dashboard managers build dashboards and share them with users or groups.
""",
    'category': 'Productivity',
    'author': "Cliff's Country Crafts",
    'website': 'https://aberbran.farm',
    'depends': ['base', 'web'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/widget_category_data.xml',
        'data/widget_type_data.xml',
        'views/dashboard_widget_category_views.xml',
        'views/dashboard_widget_type_views.xml',
        'views/dashboard_widget_views.xml',
        'views/dashboard_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_dashboard/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}

{
    'name': 'Custom Dashboards',
    'version': '19.0.1.3.0',
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
* Export to PDF: an A3 landscape print-out with the current company's
  branding, the dashboard title in the header and "1 of 3" page numbers.
  Widgets are never split across pages.
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
        'views/res_config_settings_views.xml',
        'views/menus.xml',
        'report/dashboard_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_dashboard/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
    # Not icon.png: browsers cache that URL for a week, so a new name
    # makes the Apps list pick up the current artwork.
    'icon': '/custom_dashboard/static/description/app_icon.png',
    'license': 'LGPL-3',
}

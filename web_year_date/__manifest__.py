# -*- coding: utf-8 -*-
{
    'name': 'Year Picker',
    'version': '19.0.1.0.0',
    'category': 'Hidden/Tools',
    'summary': 'A year_date field widget: a Date field picked and shown as a year only',
    'description': """
        Adds the year_date widget for Date fields. The picker opens on years,
        the field shows the year only (e.g. 2026) and the date saved is
        1 January of that year. Use it for every year selector (see
        CLAUDE.md > Dates):

            year = fields.Date(string='Year')   # store 1 January of the year
            <field name="year" widget="year_date"/>
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['web'],
    'assets': {
        'web.assets_backend': [
            'web_year_date/static/src/year_date.js',
            'web_year_date/static/src/year_date.xml',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}

from odoo.tools import sql


def migrate(cr, version):
    # Keep the old Overview widths for post-migrate (the field is gone, so
    # Odoo would drop its column).
    if sql.column_exists(cr, 'advanced_project_overview_widget', 'width'):
        sql.rename_column(cr, 'advanced_project_overview_widget', 'width', 'legacy_width')

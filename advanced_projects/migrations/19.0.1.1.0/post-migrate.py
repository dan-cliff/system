from odoo import SUPERUSER_ID, api
from odoo.tools import sql

# Old Overview widths, as columns of the 12-column grid.
WIDTHS = {'small': 4, 'medium': 6, 'large': 8, 'full': 12}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Links made before link types existed become End to Start links.
    env['advanced.project.task']._sync_all_links()
    # Overview widgets move from a width in a flowing row layout to a place on
    # the grid: laid out in their old order, row by row.
    if not sql.column_exists(cr, 'advanced_project_overview_widget', 'legacy_width'):
        return
    Widget = env['advanced.project.overview.widget']
    cr.execute("SELECT id, legacy_width FROM advanced_project_overview_widget ORDER BY project_id, sequence, id")
    rows = cr.fetchall()
    widths = dict(rows)
    for project in env['advanced.project'].with_context(active_test=False).search([]):
        widgets = Widget.browse([wid for wid, _width in rows]).filtered(lambda w: w.project_id == project)
        x = y = row_height = 0
        for widget in widgets.sorted(lambda w: (w.sequence, w.id)):
            w = WIDTHS.get(widths.get(widget.id), 4)
            h = Widget._widget_default_size(widget.widget_type)[1]
            if x + w > 12:
                x, y, row_height = 0, y + row_height, 0
            widget.write({'grid_x': x, 'grid_y': y, 'grid_w': w, 'grid_h': h})
            x += w
            row_height = max(row_height, h)
    cr.execute("ALTER TABLE advanced_project_overview_widget DROP COLUMN legacy_width")

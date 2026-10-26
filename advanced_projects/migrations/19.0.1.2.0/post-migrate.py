from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # Widgets dragged in from the palette could be saved at the palette
    # tile's width (1 or 2 columns): give them their own width back.
    env = api.Environment(cr, SUPERUSER_ID, {})
    Widget = env['advanced.project.overview.widget']
    for widget in Widget.search([('grid_w', '<', 3)]):
        width = Widget._widget_default_size(widget.widget_type)[0]
        if width > widget.grid_w:
            # keep it on the grid; the Overview moves overlapping widgets down
            widget.write({'grid_w': width, 'grid_x': min(widget.grid_x, 12 - width)})

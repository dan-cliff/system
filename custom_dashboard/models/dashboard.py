import base64
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

MANAGER_GROUP = 'custom_dashboard.group_dashboard_manager'

# PDF export: A3 landscape less the margins of paperformat_dashboard_a3 and
# the report body's container padding (12 px a side), in mm.
PDF_PAGE_WIDTH = 393.0
PDF_PAGE_HEIGHT = 248.0
PDF_GAP = 1.5
COLUMNS = 12
# On screen a grid row is 80 px; a column is a twelfth of the grid width.
DEFAULT_ROW_RATIO = 0.7
PNG_DATA_URI = re.compile(r'^data:image/(png|jpeg);base64,[A-Za-z0-9+/=]+$')


class CustomDashboard(models.Model):
    _name = 'custom.dashboard'
    _description = 'Custom Dashboard'
    _order = 'sequence, name, id'

    name = fields.Char(string='Name', required=True, translate=True)
    description = fields.Text(string='Description', translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    color = fields.Integer(string='Colour')
    refresh_interval = fields.Integer(
        string='Auto-refresh (minutes)', default=0,
        help='Reload widget data every N minutes while the dashboard is open. 0 turns it off.',
    )
    widget_ids = fields.One2many('custom.dashboard.widget', 'dashboard_id', string='Widgets')
    widget_count = fields.Integer(string='# Widgets', compute='_compute_widget_count')
    user_ids = fields.Many2many(
        'res.users', 'custom_dashboard_res_users_rel', 'dashboard_id', 'user_id',
        string='Shared with Users', domain=[('share', '=', False)],
    )
    group_ids = fields.Many2many(
        'res.groups', 'custom_dashboard_res_groups_rel', 'dashboard_id', 'group_id',
        string='Shared with Groups',
        help='Every member of these groups can view the dashboard.',
    )

    @api.depends('widget_ids')
    def _compute_widget_count(self):
        for dashboard in self:
            dashboard.widget_count = len(dashboard.widget_ids)

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for dashboard, vals in zip(self, vals_list):
            vals['name'] = _('%s (copy)', dashboard.name)
            vals['widget_ids'] = [(0, 0, data) for data in dashboard.widget_ids.copy_data()]
        return vals_list

    def action_open(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'custom_dashboard.dashboard',
            'name': self.name,
            'context': {'active_id': self.id},
            'params': {'dashboard_id': self.id},
        }

    # ------------------------------------------------------------------
    # Front-end API
    # ------------------------------------------------------------------
    @api.model
    def _can_edit(self):
        return self.env.user.has_group(MANAGER_GROUP)

    def _check_can_edit(self):
        if not self._can_edit():
            raise AccessError(_('Only dashboard managers can change dashboards.'))

    def get_dashboard(self):
        """Everything the client action needs to draw the dashboard."""
        self.ensure_one()
        can_edit = self._can_edit()
        types = self.env['custom.dashboard.widget.type'].search([])
        return {
            'id': self.id,
            'name': self.name,
            'refresh_interval': self.refresh_interval,
            'can_edit': can_edit,
            'widgets': [widget._get_config() for widget in self.widget_ids],
            'palette': [
                {
                    'code': t.code,
                    'name': t.name,
                    'icon': t.icon or 'fa-bar-chart',
                    'description': t.description or '',
                    'category': t.category_id.name or _('Other'),
                    'w': t.default_width or 4,
                    'h': t.default_height or 4,
                }
                for t in types
            ] if can_edit else [],
        }

    def save_layout(self, items):
        """Store widget positions from the editor.

        ``items`` is a list of ``{"id", "x", "y", "w", "h"}`` dicts.
        """
        self.ensure_one()
        self._check_can_edit()
        widgets = self.widget_ids
        for item in items or []:
            widget = widgets.filtered(lambda w: w.id == item.get('id'))
            if not widget:
                continue
            vals = {
                'pos_x': max(int(item.get('x') or 0), 0),
                'pos_y': max(int(item.get('y') or 0), 0),
                'width': min(max(int(item.get('w') or 1), 1), 12),
                'height': max(int(item.get('h') or 1), 1),
            }
            if any(widget[k] != v for k, v in vals.items()):
                widget.write(vals)
        return True

    def add_widget(self, type_code, x=0, y=0, w=None, h=None):
        """Create a widget of ``type_code`` at the given grid position."""
        self.ensure_one()
        self._check_can_edit()
        widget_type = self.env['custom.dashboard.widget.type'].search(
            [('code', '=', type_code)], limit=1,
        )
        if not widget_type:
            raise AccessError(_('Unknown widget type: %s', type_code))
        widget = self.env['custom.dashboard.widget'].create({
            'dashboard_id': self.id,
            'type_id': widget_type.id,
            'name': widget_type.name,
            'pos_x': max(int(x or 0), 0),
            'pos_y': max(int(y or 0), 0),
            'width': min(max(int(w or widget_type.default_width or 4), 1), 12),
            'height': max(int(h or widget_type.default_height or 4), 1),
        })
        return widget._get_config()

    # ------------------------------------------------------------------
    # PDF export
    # ------------------------------------------------------------------
    def export_pdf(self, items, row_ratio=None):
        """Render the dashboard as an A3 PDF and return it base64-encoded.

        ``items`` are ``{"id", "x", "y", "w", "h", "image"}`` dicts: the grid
        position of each widget and a PNG snapshot taken in the browser, so
        the PDF shows exactly what the user sees. ``row_ratio`` is the height
        of a grid row divided by the width of a grid column on screen.
        """
        self.ensure_one()
        self.check_access('read')
        widget_ids = set(self.widget_ids.ids)
        items = [
            item for item in items or []
            if item.get('id') in widget_ids and PNG_DATA_URI.match(item.get('image') or '')
        ]
        if not items:
            raise UserError(_('There is nothing to export on this dashboard.'))
        report = self.env.ref('custom_dashboard.action_report_dashboard_pdf')
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        data = {
            'company_id': self.env.company.id,
            'printed': now.strftime('%d/%m/%Y %H:%M'),
            'pages': self._pdf_pages(items, row_ratio),
            'page_width': PDF_PAGE_WIDTH,
            'page_height': PDF_PAGE_HEIGHT,
            'gap': PDF_GAP,
        }
        pdf, _report_type = self.env['ir.actions.report'].with_company(self.env.company)._render_qweb_pdf(
            report.report_name, self.ids, data=data,
        )
        return {
            'filename': '%s.pdf' % re.sub(r'[\\/:*?"<>|]+', '-', self.name).strip(),
            'content': base64.b64encode(pdf).decode(),
        }

    @api.model
    def _pdf_pages(self, items, row_ratio=None):
        """Lay the widgets out on pages, keeping the dashboard's arrangement.

        Widgets keep their columns and rows. When a widget would cross the
        bottom of a page, a new page starts at that widget's row, so no
        widget is ever cut in two. A widget taller than a page is shrunk to
        fit one page.
        """
        try:
            ratio = float(row_ratio or DEFAULT_ROW_RATIO)
        except (TypeError, ValueError):
            ratio = DEFAULT_ROW_RATIO
        ratio = min(max(ratio, 0.2), 2.0)
        col_mm = PDF_PAGE_WIDTH / COLUMNS
        row_mm = col_mm * ratio

        def number(item, key, low, high, default):
            try:
                return min(max(int(item.get(key)), low), high)
            except (TypeError, ValueError):
                return default

        widgets = []
        for item in items:
            w = number(item, 'w', 1, COLUMNS, COLUMNS)
            widgets.append({
                'x': number(item, 'x', 0, COLUMNS - w, 0),
                'y': number(item, 'y', 0, 10000, 0),
                'w': w,
                'h': number(item, 'h', 1, 1000, 1),
                'image': item['image'],
            })
        widgets.sort(key=lambda widget: (widget['y'], widget['x']))

        pages = []
        start = None
        for widget in widgets:
            widget['height'] = min(widget['h'] * row_mm, PDF_PAGE_HEIGHT)
            if start is None or (widget['y'] - start) * row_mm + widget['height'] > PDF_PAGE_HEIGHT + 0.01:
                # Start the next page at this widget's row, taking along the
                # widgets of the same row already placed, so rows stay whole.
                start = widget['y']
                moved = [other for other in pages[-1] if other['y'] >= start] if pages else []
                if moved:
                    pages[-1] = [other for other in pages[-1] if other['y'] < start]
                pages.append(moved)
            pages[-1].append(widget)
        return [
            [
                {
                    'left': round(widget['x'] * col_mm, 2),
                    'top': round((widget['y'] - min(other['y'] for other in page)) * row_mm, 2),
                    'width': round(widget['w'] * col_mm, 2),
                    'height': round(widget['height'], 2),
                    'image': widget['image'],
                }
                for widget in page
            ]
            for page in pages if page
        ]

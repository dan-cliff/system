from odoo import _, api, fields, models
from odoo.exceptions import AccessError

MANAGER_GROUP = 'custom_dashboard.group_dashboard_manager'


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

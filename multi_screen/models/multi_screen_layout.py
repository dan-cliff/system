from odoo import api, fields, models


class MultiScreenLayout(models.Model):
    """A workspace: a saved set of windows spread across the user's screens."""

    _name = 'multi.screen.layout'
    _description = 'Multi-Screen Workspace'
    _order = 'sequence, name, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    user_id = fields.Many2one(
        'res.users', string='Owner', index=True, ondelete='cascade',
        default=lambda self: self.env.user,
        help='Leave empty to share this workspace with everyone (administrators only).',
    )
    launch_on_start = fields.Boolean(
        string='Open on launch',
        help='Open this workspace automatically when the installed Odoo app starts. '
             'Only one of your workspaces can be opened on launch; a shared one is '
             'used when you have none of your own.',
    )
    note = fields.Text()
    trigger_model_ids = fields.Many2many(
        'ir.model', 'multi_screen_layout_trigger_model_rel', 'layout_id', 'model_id',
        string='Open when opening',
        domain=[('transient', '=', False)],
        help='Open this workspace automatically when one of these is opened '
             '(e.g. Sales Order). The window it is opened from stays on what was '
             'opened; the workspace\'s other windows open on their screens.',
    )
    trigger_view_type_ids = fields.Many2many(
        'multi.screen.view.type', 'multi_screen_layout_trigger_view_type_rel', 'layout_id', 'view_type_id',
        string='In these views',
        help='Only when opened in these views (e.g. List). Leave empty for any view.',
    )
    window_ids = fields.One2many('multi.screen.window', 'layout_id', string='Windows', copy=True)
    window_count = fields.Integer(string='Windows', compute='_compute_window_count')
    screen_count = fields.Integer(
        string='Screens needed', compute='_compute_window_count',
        help='The highest screen number any of its windows uses.',
    )

    @api.depends('window_ids.screen_number')
    def _compute_window_count(self):
        for layout in self:
            layout.window_count = len(layout.window_ids)
            layout.screen_count = max(layout.window_ids.mapped('screen_number') or [0])

    @api.model_create_multi
    def create(self, vals_list):
        layouts = super().create(vals_list)
        layouts.filtered('launch_on_start')._keep_single_launch()
        return layouts

    def write(self, vals):
        res = super().write(vals)
        if vals.get('launch_on_start') or 'user_id' in vals:
            self.filtered('launch_on_start')._keep_single_launch()
        return res

    def _keep_single_launch(self):
        """Only one workspace per owner (or one shared one) opens on launch."""
        for layout in self:
            self.search([
                ('id', '!=', layout.id),
                ('user_id', '=', layout.user_id.id),
                ('launch_on_start', '=', True),
            ]).write({'launch_on_start': False})

    def action_open(self):
        """Open the workspace's windows; placing windows happens in the browser."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'multi_screen.open_workspace',
            'params': {'layout_id': self.id},
        }

    # ------------------------------------------------------------------
    # API for the web client (multi_screen_service.js)
    # ------------------------------------------------------------------
    @api.model
    def get_workspaces(self):
        """The current user's workspaces and the shared ones, with their windows.

        Returns ``{"launch_layout_id": id | False, "layouts": [...]}``; the
        launch workspace is the user's own, else the shared one.
        """
        layouts = self.search(['|', ('user_id', '=', self.env.uid), ('user_id', '=', False)])
        own_launch = layouts.filtered(lambda l: l.launch_on_start and l.user_id)
        launch = own_launch or layouts.filtered(lambda l: l.launch_on_start and not l.user_id)
        return {
            'launch_layout_id': launch[:1].id,
            'layouts': [layout._workspace_data() for layout in layouts],
        }

    def _workspace_data(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'shared': not self.user_id,
            'screen_count': self.screen_count,
            'trigger_models': self.trigger_model_ids.mapped('model'),
            'trigger_view_types': self.trigger_view_type_ids.mapped('code'),
            'windows': [window._window_data() for window in self.window_ids],
        }

    @api.model
    def save_from_windows(self, windows):
        """Save the windows open now as a new workspace for the current user.

        ``windows`` comes from the web client, the window that asked first:
        ``[{"screen_number", "left_pct", "top_pct", "width_pct", "height_pct",
        "url"}, ...]``. Returns an action opening the new workspace so it can
        be renamed.
        """
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        layout = self.create({
            'name': self.env._('Workspace %s', now.strftime('%d/%m/%Y %H:%M')),
            'window_ids': [
                (0, 0, self.env['multi.screen.window']._values_from_client(index, window))
                for index, window in enumerate(windows or [])
            ],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Saved workspace'),
            'res_model': self._name,
            'res_id': layout.id,
            'views': [(False, 'form')],
            'target': 'new',
        }

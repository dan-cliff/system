from odoo import api, fields, models


class HomeToolbox(models.Model):
    _name = 'home.toolbox'
    _description = 'Home Screen Toolbox'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    icon = fields.Char(
        string='Icon',
        default='fa-folder',
        help='FontAwesome icon class used for the folder tile (e.g. fa-folder, fa-briefcase).',
    )
    color = fields.Char(
        string='Colour',
        default='#714B67',
        help='Background colour of the folder tile (hex, e.g. #714B67).',
    )
    active = fields.Boolean(string='Active', default=True)
    user_id = fields.Many2one(
        'res.users',
        string='User',
        ondelete='cascade',
        index=True,
        help='Leave empty for the global default layout shown to everyone. '
             'When set, this toolbox is a personal override for that user only.',
    )
    app_ids = fields.One2many('home.toolbox.app', 'toolbox_id', string='Apps')
    app_count = fields.Integer(string='# Apps', compute='_compute_app_count')

    @api.depends('app_ids')
    def _compute_app_count(self):
        for toolbox in self:
            toolbox.app_count = len(toolbox.app_ids)

    @api.depends('name', 'user_id')
    def _compute_display_name(self):
        for toolbox in self:
            label = toolbox.name or ''
            if not toolbox.user_id:
                label = '%s (Global default)' % label if label else 'Global default'
            toolbox.display_name = label

    # ------------------------------------------------------------------
    # Layout API (called from the front-end launcher)
    # ------------------------------------------------------------------
    @api.model
    def _resolve_toolboxes(self):
        """Return the recordset of toolboxes effective for the current user.

        A user's own override records win; otherwise the global default
        (user_id = False); otherwise an empty recordset.
        """
        own = self.search([('user_id', '=', self.env.uid)])
        if own:
            return own
        return self.search([('user_id', '=', False)])

    @api.model
    def get_home_layout(self):
        """Resolve the launcher layout for the current user.

        Returns a dict::

            {
                "source": "user" | "global" | "none",
                "toolboxes": [
                    {"id", "name", "icon", "color", "sequence",
                     "apps": [{"menu_id", "xmlid"}, ...]},
                    ...
                ],
            }
        """
        own = self.search([('user_id', '=', self.env.uid)])
        if own:
            source, toolboxes = 'user', own
        else:
            toolboxes = self.search([('user_id', '=', False)])
            source = 'global' if toolboxes else 'none'

        data = []
        for toolbox in toolboxes:
            apps = []
            for line in toolbox.app_ids:
                if not line.menu_id:
                    continue
                apps.append({
                    'menu_id': line.menu_id.id,
                    'xmlid': line.menu_xmlid or '',
                })
            data.append({
                'id': toolbox.id,
                'name': toolbox.name,
                'icon': toolbox.icon or 'fa-folder',
                'color': toolbox.color or '#714B67',
                'sequence': toolbox.sequence,
                'apps': apps,
            })
        return {'source': source, 'toolboxes': data}

    @api.model
    def set_home_layout(self, toolboxes):
        """Persist the current user's personal override from the editor.

        ``toolboxes`` is a list of dicts::

            [{"name", "icon", "color", "sequence", "app_menu_ids": [id, ...]}, ...]

        Any existing override for the user is replaced atomically. Passing an
        empty list clears the override (falls back to the global default).
        """
        uid = self.env.uid
        self.search([('user_id', '=', uid)]).unlink()
        for index, tb in enumerate(toolboxes or []):
            menu_ids = [m for m in (tb.get('app_menu_ids') or []) if m]
            self.create({
                'name': tb.get('name') or 'Toolbox',
                'icon': tb.get('icon') or 'fa-folder',
                'color': tb.get('color') or '#714B67',
                'sequence': tb.get('sequence', (index + 1) * 10),
                'user_id': uid,
                'app_ids': [
                    (0, 0, {'menu_id': menu_id, 'sequence': line_index})
                    for line_index, menu_id in enumerate(menu_ids)
                ],
            })
        return True

    @api.model
    def reset_my_layout(self):
        """Remove the current user's override so the global default applies."""
        self.search([('user_id', '=', self.env.uid)]).unlink()
        return True


class HomeToolboxApp(models.Model):
    _name = 'home.toolbox.app'
    _description = 'Home Screen Toolbox App'
    _order = 'sequence, id'

    toolbox_id = fields.Many2one(
        'home.toolbox', string='Toolbox', required=True, ondelete='cascade', index=True,
    )
    menu_id = fields.Many2one(
        'ir.ui.menu',
        string='App',
        required=True,
        ondelete='cascade',
        domain="[('parent_id', '=', False)]",
        help='Top-level application menu shown on the home screen.',
    )
    menu_xmlid = fields.Char(string='App XML ID', compute='_compute_menu_xmlid', store=True)
    sequence = fields.Integer(string='Sequence', default=10)

    @api.depends('menu_id')
    def _compute_menu_xmlid(self):
        for line in self:
            line.menu_xmlid = line.menu_id.get_external_id().get(line.menu_id.id, '') if line.menu_id else ''

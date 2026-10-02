from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class HomeMenuFolder(models.Model):
    _name = 'home.menu.folder'
    _description = 'Home Screen Folder'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    icon = fields.Char(
        string='Icon',
        default='fa-folder',
        help='FontAwesome icon class shown on the folder tile while it is empty (e.g. fa-folder, fa-briefcase).',
    )
    color = fields.Char(
        string='Colour',
        default='#714B67',
        help='Background colour of the folder tile.',
    )
    active = fields.Boolean(string='Active', default=True)
    user_id = fields.Many2one(
        'res.users',
        string='User',
        ondelete='cascade',
        index=True,
        help='Leave empty for the default layout shown to everyone. '
             'When set, this folder belongs to that user\'s personal layout, '
             'which replaces the default layout for them.',
    )
    app_ids = fields.One2many('home.menu.folder.app', 'folder_id', string='Apps')
    app_count = fields.Integer(string='# Apps', compute='_compute_app_count')

    @api.depends('app_ids')
    def _compute_app_count(self):
        for folder in self:
            folder.app_count = len(folder.app_ids)

    @api.depends('name', 'user_id')
    def _compute_display_name(self):
        for folder in self:
            label = folder.name or ''
            if not folder.user_id:
                label = _('%s (Default)', label) if label else _('Default')
            folder.display_name = label

    # ------------------------------------------------------------------
    # Layout API (called from the home screen)
    # ------------------------------------------------------------------
    def _layout_domain(self, scope):
        return [('user_id', '=', self.env.uid if scope == 'user' else False)]

    def _check_can_edit_default(self):
        if not self.env.user.has_group('base.group_erp_manager'):
            raise AccessError(_('Only administrators can change the default home screen layout.'))

    @api.model
    def get_home_layout(self):
        """Resolve the home screen layout for the current user.

        The user's personal folders win; otherwise the default layout
        (folders with no user); otherwise no folders at all.

        Returns::

            {
                "source": "user" | "default" | "none",
                "can_edit_default": bool,
                "folders": [{"id", "name", "icon", "color", "sequence",
                             "app_menu_ids": [menu_id, ...]}, ...],
            }
        """
        folders = self.search(self._layout_domain('user'))
        source = 'user'
        if not folders:
            folders = self.search(self._layout_domain('default'))
            source = 'default' if folders else 'none'
        return {
            'source': source,
            'can_edit_default': self.env.user.has_group('base.group_erp_manager'),
            'folders': [{
                'id': folder.id,
                'name': folder.name,
                'icon': folder.icon or 'fa-folder',
                'color': folder.color or '#714B67',
                'sequence': folder.sequence,
                'app_menu_ids': folder.app_ids.menu_id.ids,
            } for folder in folders],
        }

    @api.model
    def set_home_layout(self, folders, scope='user'):
        """Replace a layout with the folders edited on the home screen.

        ``scope`` is "user" (the current user's personal layout) or
        "default" (the layout for everyone without one; administrators
        only). ``folders`` is a list of dicts::

            [{"name", "icon", "color", "app_menu_ids": [menu_id, ...]}, ...]

        Saving a personal layout with no folders leaves the user on the
        default layout.
        """
        if scope == 'default':
            self._check_can_edit_default()
        user_id = self.env.uid if scope == 'user' else False
        self.with_context(active_test=False).search(self._layout_domain(scope)).unlink()
        vals_list = []
        for index, folder in enumerate(folders or []):
            menu_ids = [menu_id for menu_id in (folder.get('app_menu_ids') or []) if menu_id]
            vals_list.append({
                'name': folder.get('name') or _('Folder'),
                'icon': folder.get('icon') or 'fa-folder',
                'color': folder.get('color') or '#714B67',
                'sequence': (index + 1) * 10,
                'user_id': user_id,
                'app_ids': [
                    (0, 0, {'menu_id': menu_id, 'sequence': line_index})
                    for line_index, menu_id in enumerate(menu_ids)
                ],
            })
        self.create(vals_list)
        return True

    @api.model
    def reset_my_layout(self):
        """Remove the current user's personal layout so the default applies."""
        self.with_context(active_test=False).search(self._layout_domain('user')).unlink()
        return True


class HomeMenuFolderApp(models.Model):
    _name = 'home.menu.folder.app'
    _description = 'Home Screen Folder App'
    _order = 'sequence, id'

    folder_id = fields.Many2one(
        'home.menu.folder', string='Folder', required=True, ondelete='cascade', index=True,
    )
    menu_id = fields.Many2one(
        'ir.ui.menu',
        string='App',
        required=True,
        ondelete='cascade',
        domain="[('parent_id', '=', False)]",
        help='Top-level app shown on the home screen.',
    )
    sequence = fields.Integer(string='Sequence', default=10)

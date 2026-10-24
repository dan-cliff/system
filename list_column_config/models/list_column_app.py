from collections import Counter

from odoo import api, fields, models

ADMIN_GROUP = 'list_column_config.group_list_column_admin'
VERSION_PARAM = 'list_column_config.version'


class ListColumnApp(models.Model):
    """One per app (top-level menu), holding the app's "List Columns:
    Customise" privilege and its "Allowed" group. Kept in step with the
    installed apps by _sync_apps(); one extra record (is_fallback) covers
    lists opened outside any app."""
    _name = 'list.column.app'
    _description = 'List Columns App Permission'
    _order = 'is_fallback, name'

    name = fields.Char(string='App', required=True, readonly=True)
    menu_id = fields.Many2one(
        comodel_name='ir.ui.menu',
        string='App Menu',
        ondelete='set null',
        readonly=True,
        index=True,
    )
    is_fallback = fields.Boolean(
        string='Outside Apps',
        readonly=True,
        help='Covers lists opened outside any app (e.g. from the home screen).',
    )
    privilege_id = fields.Many2one(
        comodel_name='res.groups.privilege',
        string='Privilege',
        readonly=True,
        ondelete='set null',
    )
    group_id = fields.Many2one(
        comodel_name='res.groups',
        string='Allowed Group',
        readonly=True,
        ondelete='set null',
    )
    category_id = fields.Many2one(
        related='privilege_id.category_id',
        string='Privilege Category',
    )
    user_ids = fields.Many2many(
        related='group_id.all_user_ids',
        string='Users',
    )

    _menu_uniq = models.Constraint('UNIQUE(menu_id)', 'Each app has one List Columns permission.')

    # ── Sync with the installed apps ─────────────────────────────────────

    @api.model
    def _sync_apps(self):
        """Create the privilege and group of every app that has none, rename
        them with their app, and remove those of apps that are gone."""
        self = self.sudo().with_context(active_test=False)
        roots = self.env['ir.ui.menu'].sudo().with_context(active_test=True, lang='en_US').search([('parent_id', '=', False)])
        apps = self.search([])
        by_menu = {app.menu_id.id: app for app in apps if app.menu_id}

        for menu in roots:
            app = by_menu.get(menu.id)
            if app:
                if app.name != menu.name:
                    app.name = menu.name
                    app.privilege_id.name = self._privilege_name(menu.name)
            else:
                self._create_app(menu.name, menu=menu)
        if not apps.filtered('is_fallback'):
            self._create_app(self.env._('Outside Apps'), fallback=True)

        apps.filtered(lambda app: not app.menu_id and not app.is_fallback)._remove()
        return True

    @api.model
    def _privilege_name(self, app_name):
        return self.env._('%s List Columns: Customise', app_name)

    @api.model
    def _create_app(self, name, menu=None, fallback=False):
        category = self._app_category(menu) if menu else False
        category = category or self.env.ref('list_column_config.module_category_list_column_config')
        description = self.env._(
            'Customise the columns of the list views in %s, for all users.', name)
        privilege = self.env['res.groups.privilege'].create({
            'name': self._privilege_name(name),
            'category_id': category.id,
            'sequence': 900,
            'description': description,
        })
        group = self.env['res.groups'].create({
            'name': self.env._('Allowed'),
            'privilege_id': privilege.id,
            'comment': description,
            'implied_ids': [(4, self.env.ref('list_column_config.group_list_column_user').id)],
        })
        self.env.ref(ADMIN_GROUP).write({'implied_ids': [(4, group.id)]})
        return self.create({
            'name': name,
            'menu_id': menu.id if menu else False,
            'is_fallback': fallback,
            'privilege_id': privilege.id,
            'group_id': group.id,
        })

    @api.model
    def _app_category(self, menu):
        """The privilege category of the module that defines the app menu
        (the one most of that module's privileges use). False for apps whose
        module has no privileges of its own, and for base's (Settings, Apps):
        those go under List Columns."""
        Data = self.env['ir.model.data'].sudo()
        menu_data = Data.search([('model', '=', 'ir.ui.menu'), ('res_id', '=', menu.id)], limit=1)
        if not menu_data or menu_data.module == 'base':
            return False
        privilege_ids = Data.search([
            ('model', '=', 'res.groups.privilege'),
            ('module', '=', menu_data.module),
        ]).mapped('res_id')
        privileges = self.env['res.groups.privilege'].sudo().browse(privilege_ids).exists()
        counts = Counter(privileges.category_id.ids)
        if counts:
            return self.env['ir.module.category'].browse(counts.most_common(1)[0][0])
        return False

    def _remove(self):
        """Delete the apps with their privilege and group."""
        groups = self.group_id
        privileges = self.privilege_id
        self.unlink()
        groups.unlink()
        privileges.unlink()

    def action_sync_apps(self):
        self._sync_apps()
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    # ── Access checks ─────────────────────────────────────────────────────

    @api.model
    def _get_app(self, menu_id):
        """The app a list opened from the given top-level menu belongs to."""
        apps = self.sudo().with_context(active_test=False)
        if menu_id:
            app = apps.search([('menu_id', '=', menu_id)], limit=1)
            if not app and self.env['ir.ui.menu'].sudo().browse(menu_id).exists().filtered(lambda m: not m.parent_id):
                self._sync_apps()
                app = apps.search([('menu_id', '=', menu_id)], limit=1)
            if app:
                return app
        app = apps.search([('is_fallback', '=', True)], limit=1)
        if not app:
            self._sync_apps()
            app = apps.search([('is_fallback', '=', True)], limit=1)
        return app

    def _user_can_customise(self):
        self.ensure_one()
        user = self.env.user
        return user.has_group(ADMIN_GROUP) or (
            bool(self.group_id) and self.group_id.id in user._get_group_ids())

    @api.model
    def _session_info(self):
        user = self.env.user
        apps = self.sudo().with_context(active_test=False).search([
            ('group_id', 'in', list(user._get_group_ids())),
        ])
        return {
            'version': int(self.env['ir.config_parameter'].sudo().get_param(VERSION_PARAM, 0) or 0),
            'all': user.has_group(ADMIN_GROUP),
            'app_ids': apps.menu_id.ids,
            'fallback': any(apps.mapped('is_fallback')),
        }

    @api.model
    def _views_changed(self):
        """Saved layouts changed: rebuild the cached views, and give browsers a
        new cache key so every user loads the new columns."""
        self.env.registry.clear_cache('templates')
        params = self.env['ir.config_parameter'].sudo()
        version = int(params.get_param(VERSION_PARAM, 0) or 0) + 1
        params.set_param(VERSION_PARAM, version)
        return version

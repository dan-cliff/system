from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CustomDashboard(models.Model):
    _name = 'custom.dashboard'
    _inherit = ['custom.dashboard', 'website.published.multi.mixin', 'website.seo.metadata']

    website_data_user_id = fields.Many2one(
        'res.users', string='Show Data As',
        domain=[('share', '=', False)],
        default=lambda self: self.env.user,
        help="Website visitors see the data this user can see. Pick a user "
             "whose access is limited to what may be made public.",
    )
    website_show_in_menu = fields.Boolean(
        string='Add to Website Menu',
        help='Show a link to this dashboard in the website menu while it is published.',
    )
    website_menu_id = fields.Many2one(
        'website.menu', string='Website Menu Item', readonly=True, copy=False, ondelete='set null',
    )

    @api.depends('name')
    def _compute_website_url(self):
        for dashboard in self:
            if dashboard.id:
                dashboard.website_url = '/dashboards/%s' % self.env['ir.http']._slug(dashboard)
            else:
                dashboard.website_url = '#'

    @api.constrains('is_published', 'website_data_user_id')
    def _check_website_data_user(self):
        for dashboard in self:
            if dashboard.is_published and not dashboard.website_data_user_id:
                raise ValidationError(_(
                    'Choose whose access rights the published dashboard "%s" reads data with.',
                    dashboard.name,
                ))

    # ------------------------------------------------------------------
    # Website menu
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        dashboards = super().create(vals_list)
        dashboards._sync_website_menu()
        return dashboards

    def write(self, vals):
        res = super().write(vals)
        if {'is_published', 'website_published', 'website_show_in_menu', 'website_id', 'name', 'active'} & set(vals):
            self._sync_website_menu()
        return res

    def unlink(self):
        self.website_menu_id.sudo().unlink()
        return super().unlink()

    def _sync_website_menu(self):
        """Create, update or remove each dashboard's website menu item."""
        Menu = self.env['website.menu'].sudo()
        for dashboard in self:
            menu = dashboard.website_menu_id.sudo()
            wanted = dashboard.active and dashboard.is_published and dashboard.website_show_in_menu
            if not wanted:
                if menu:
                    menu.unlink()
                continue
            website = dashboard.website_id or self.env['website'].get_current_website()
            vals = {
                'name': dashboard.name,
                'url': dashboard.website_url,
                'website_id': website.id,
            }
            if menu and menu.website_id == website:
                menu.write(vals)
            else:
                if menu:
                    menu.unlink()
                menu = Menu.create({**vals, 'parent_id': website.menu_id.id, 'sequence': 60})
                dashboard.sudo().website_menu_id = menu

    # ------------------------------------------------------------------
    # Public data
    # ------------------------------------------------------------------
    def _get_public_dashboard(self):
        """Layout, widget settings and data for the public page.

        Call on a sudo-ed record. Widget data is read as the configured
        data user, so their access rights and record rules apply.
        """
        self.ensure_one()
        widgets = self.widget_ids
        configs = []
        for widget in widgets:
            config = widget._get_config()
            if config.get('image_url'):
                config['image_url'] = '/dashboards/%s/image/%s?unique=%s' % (
                    self.id, widget.id, int(widget.write_date.timestamp()) if widget.write_date else 0,
                )
            configs.append(config)
        data_user = self.website_data_user_id
        data_env = self.env(user=data_user.id, su=False, context=dict(self.env.context, lang=self.env.lang))
        return {
            'id': self.id,
            'name': self.name,
            'refresh_interval': self.refresh_interval,
            'widgets': configs,
            'data': widgets._get_widget_data(data_env) if data_user else {},
        }

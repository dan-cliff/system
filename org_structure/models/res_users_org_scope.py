from odoo import api, fields, models
from odoo.fields import Domain

# Top-level menus shown as apps on the home screen.
APP_MENU_DOMAIN = [('parent_id', '=', False), ('web_icon', '!=', False)]


class ResUsersOrgScope(models.Model):
    """App Specific Scoping: limit one app's records for one user.

    Units picked across levels are cumulative (OR-ed): records linked to any
    selected Division, Business Unit, Location or Department are visible,
    whether or not those units sit under each other.
    """
    _name = 'res.users.org.scope'
    _description = 'User App Specific Organisation Scoping'
    _order = 'user_id, menu_sequence, menu_id'

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        required=True,
        index=True,
        ondelete='cascade',
    )
    menu_id = fields.Many2one(
        comodel_name='ir.ui.menu',
        string='App',
        required=True,
        ondelete='cascade',
        domain=APP_MENU_DOMAIN,
    )
    menu_sequence = fields.Integer(related='menu_id.sequence', store=True)
    app_icon = fields.Binary(related='menu_id.web_icon_data', string='Icon')
    division_ids = fields.Many2many(
        comodel_name='org.division',
        relation='res_users_org_scope_division_rel',
        column1='scope_id',
        column2='division_id',
        string='Divisions',
    )
    business_unit_ids = fields.Many2many(
        comodel_name='org.business.unit',
        relation='res_users_org_scope_business_unit_rel',
        column1='scope_id',
        column2='business_unit_id',
        string='Business Units',
    )
    location_ids = fields.Many2many(
        comodel_name='org.location',
        relation='res_users_org_scope_location_rel',
        column1='scope_id',
        column2='location_id',
        string='Locations',
    )
    department_ids = fields.Many2many(
        comodel_name='org.department',
        relation='res_users_org_scope_department_rel',
        column1='scope_id',
        column2='department_id',
        string='Departments',
    )
    unit_count = fields.Integer(string='Org Units', compute='_compute_unit_count')

    _user_menu_uniq = models.Constraint(
        'unique(user_id, menu_id)',
        'This app already has scoping for this user.',
    )

    @api.depends('division_ids', 'business_unit_ids', 'location_ids', 'department_ids')
    def _compute_unit_count(self):
        for rec in self:
            rec.unit_count = (len(rec.division_ids) + len(rec.business_unit_ids)
                              + len(rec.location_ids) + len(rec.department_ids))

    @api.model
    def _sync_app_lines(self, users=None):
        """Give every internal user one line per installed app.

        Missing lines are added and lines for menus that are no longer apps
        are removed, so each user's App Specific Scoping always lists every
        app. A line with no org units selected leaves that app unscoped.
        """
        self = self.sudo()
        if users is None:
            users = self.env['res.users'].sudo().with_context(active_test=False).search(
                [('share', '=', False)])
        else:
            users = users.sudo().filtered(lambda user: not user.share)
        apps = self.env['ir.ui.menu'].sudo().search(APP_MENU_DOMAIN)
        existing = self.search([('user_id', 'in', users.ids)])
        stale = existing.filtered(lambda line: line.menu_id not in apps)
        if stale:
            stale.unlink()
        have = {(line.user_id.id, line.menu_id.id) for line in existing - stale}
        missing = [
            {'user_id': user.id, 'menu_id': app.id}
            for user in users
            for app in apps
            if (user.id, app.id) not in have
        ]
        if missing:
            self.create(missing)

    def _get_app_models(self):
        """Models opened by window actions anywhere under this app's menus."""
        self.ensure_one()
        menus = self.env['ir.ui.menu'].sudo().search([('id', 'child_of', self.menu_id.id)])
        return {
            menu.action.res_model
            for menu in menus
            if menu.action and menu.action._name == 'ir.actions.act_window' and menu.action.res_model
        }

    def _get_record_domain(self):
        """Cumulative domain for scoped records, or None when no units are set."""
        self.ensure_one()
        domains = [
            Domain(field, 'in', self[units].ids)
            for field, units in (
                ('org_division_id', 'division_ids'),
                ('org_business_unit_id', 'business_unit_ids'),
                ('org_location_id', 'location_ids'),
                ('org_department_id', 'department_ids'),
            )
            if self[units]
        ]
        return Domain.OR(domains) if domains else None

    # Record rules are cached per user: drop the cache when scoping changes.
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env.registry.clear_cache()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.env.registry.clear_cache()
        return res

    def unlink(self):
        res = super().unlink()
        self.env.registry.clear_cache()
        return res

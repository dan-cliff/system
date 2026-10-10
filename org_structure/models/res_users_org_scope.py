from odoo import api, fields, models
from odoo.fields import Domain

from .org_scope_mixin import OrgScopeMixin

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
    _order = 'user_id, app_name, id'

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
    app_name = fields.Char(related='menu_id.name', string='App Name', store=True)
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
    org_show_division = fields.Boolean(compute='_compute_org_show')
    org_show_business_unit = fields.Boolean(compute='_compute_org_show')
    org_show_location = fields.Boolean(compute='_compute_org_show')
    org_show_department = fields.Boolean(compute='_compute_org_show')
    _compute_org_show = OrgScopeMixin._compute_org_show

    # What is actually enforced for this app: the user's "scope all apps"
    # unit when one is ticked (it overrides this line), else this line's units.
    scoped_all_apps = fields.Boolean(compute='_compute_effective_units')
    effective_division_ids = fields.Many2many(
        comodel_name='org.division', string='Divisions', compute='_compute_effective_units')
    effective_business_unit_ids = fields.Many2many(
        comodel_name='org.business.unit', string='Business Units', compute='_compute_effective_units')
    effective_location_ids = fields.Many2many(
        comodel_name='org.location', string='Locations', compute='_compute_effective_units')
    effective_department_ids = fields.Many2many(
        comodel_name='org.department', string='Departments', compute='_compute_effective_units')

    _user_menu_uniq = models.Constraint(
        'unique(user_id, menu_id)',
        'This app already has scoping for this user.',
    )

    @api.depends('division_ids', 'business_unit_ids', 'location_ids', 'department_ids',
                 'user_id.org_scope_level', 'user_id.home_division_id', 'user_id.home_business_unit_id',
                 'user_id.home_location_id', 'user_id.home_department_id')
    def _compute_effective_units(self):
        for rec in self:
            level = rec.user_id.org_scope_level
            rec.scoped_all_apps = bool(level)
            for name in ('division', 'business_unit', 'location', 'department'):
                if level:
                    units = rec.user_id[f'home_{name}_id'] if name == level else rec[f'{name}_ids'].browse()
                else:
                    units = rec[f'{name}_ids']
                rec[f'effective_{name}_ids'] = units

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
        # Callers may pass active_test=False (e.g. ir.ui.menu.unlink); only active apps count.
        apps = self.env['ir.ui.menu'].sudo().with_context(active_test=True).search(APP_MENU_DOMAIN)
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
        """Models opened by window or server actions anywhere under this app's menus."""
        self.ensure_one()
        menus = self.env['ir.ui.menu'].sudo().search([('id', 'child_of', self.menu_id.id)])
        models = set()
        for menu in menus:
            action = menu.action
            if not action:
                continue
            if action._name == 'ir.actions.act_window' and action.res_model:
                models.add(action.res_model)
            elif action._name == 'ir.actions.server' and action.model_id:
                models.add(action.model_id.model)
        return models

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

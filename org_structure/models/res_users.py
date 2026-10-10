from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

from .org_scope_mixin import ORG_LEVELS, OrgScopeMixin

LEVEL_LABELS = {
    'division': 'Division',
    'business_unit': 'Business Unit',
    'location': 'Location',
    'department': 'Department',
}
ORG_FIELDS = (
    'home_division_id', 'home_business_unit_id', 'home_location_id', 'home_department_id',
    'org_scope_level', 'org_app_scope_ids',
)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Users inherit their contact's Organisation fields; the user form has
    # its own Organisation tab (home units), so no automatic section.
    _org_form_section = False

    # Which levels the Organisation tab shows (enabled levels with units).
    org_show_division = fields.Boolean(compute='_compute_org_show')
    org_show_business_unit = fields.Boolean(compute='_compute_org_show')
    org_show_location = fields.Boolean(compute='_compute_org_show')
    org_show_department = fields.Boolean(compute='_compute_org_show')
    _compute_org_show = OrgScopeMixin._compute_org_show

    home_division_id = fields.Many2one(
        comodel_name='org.division',
        string='Home Division',
        ondelete='set null',
        domain="[('company_id', 'in', company_ids)]",
    )
    home_business_unit_id = fields.Many2one(
        comodel_name='org.business.unit',
        string='Home Business Unit',
        ondelete='set null',
        domain="[('company_id', 'in', company_ids), ('division_id', '=?', home_division_id)]",
    )
    home_location_id = fields.Many2one(
        comodel_name='org.location',
        string='Home Location',
        ondelete='set null',
        domain="[('company_id', 'in', company_ids), ('business_unit_id', '=?', home_business_unit_id)]",
    )
    home_department_id = fields.Many2one(
        comodel_name='org.department',
        string='Home Department',
        ondelete='set null',
        domain="[('company_id', 'in', company_ids), ('location_id', '=?', home_location_id)]",
    )
    # Technical: the one level (if any) all apps are scoped to. The checkboxes
    # below are views onto it, so only one level can ever be ticked.
    org_scope_level = fields.Selection(
        selection=list(LEVEL_LABELS.items()),
        string='Scope All Apps To',
    )
    org_scope_division = fields.Boolean(
        string='Scope all apps to this Division',
        compute='_compute_org_scope_flags', readonly=False,
    )
    org_scope_business_unit = fields.Boolean(
        string='Scope all apps to this Business Unit',
        compute='_compute_org_scope_flags', readonly=False,
    )
    org_scope_location = fields.Boolean(
        string='Scope all apps to this Location',
        compute='_compute_org_scope_flags', readonly=False,
    )
    org_scope_department = fields.Boolean(
        string='Scope all apps to this Department',
        compute='_compute_org_scope_flags', readonly=False,
    )
    org_app_scope_ids = fields.One2many(
        comodel_name='res.users.org.scope',
        inverse_name='user_id',
        string='App Specific Scoping',
    )

    # ------------------------------------------------------------------
    # Scope checkboxes
    # ------------------------------------------------------------------

    @api.depends('org_scope_level')
    def _compute_org_scope_flags(self):
        for user in self:
            for level in ORG_LEVELS:
                user[f'org_scope_{level}'] = user.org_scope_level == level

    @staticmethod
    def _org_scope_level_from_flags(current, flags):
        """The single scoped level after ticking/unticking ``flags``.

        ``flags`` maps levels to their new checkbox value; levels missing from
        it keep their current state. A newly ticked level wins over the
        current one, so only one level is ever scoped.
        """
        newly_ticked = [level for level in ORG_LEVELS if flags.get(level) and level != current]
        if newly_ticked:
            return newly_ticked[0]
        return current if current and flags.get(current, True) else False

    def _pop_org_scope_flags(self, vals):
        return {level: vals.pop(f'org_scope_{level}') for level in ORG_LEVELS
                if f'org_scope_{level}' in vals}

    @api.onchange('org_scope_division', 'org_scope_business_unit',
                  'org_scope_location', 'org_scope_department')
    def _onchange_org_scope_flags(self):
        for user in self:
            user.org_scope_level = self._org_scope_level_from_flags(
                user.org_scope_level,
                {level: user[f'org_scope_{level}'] for level in ORG_LEVELS},
            )

    # ------------------------------------------------------------------
    # Home hierarchy: picking a lower level fills the levels above it,
    # changing a higher level clears the levels below that don't belong.
    # ------------------------------------------------------------------

    def _org_home_changed(self, level):
        """``level``'s home unit changed: fill the levels above it from the
        unit's own links and clear lower home units that don't fit."""
        for user in self:
            unit = user[f'home_{level}_id']
            index = ORG_LEVELS.index(level)
            if unit:
                for higher in ORG_LEVELS[:index]:
                    user[f'home_{higher}_id'] = unit[f'{higher}_id']
            for lower in ORG_LEVELS[index + 1:]:
                lower_unit = user[f'home_{lower}_id']
                ancestor = lower_unit[f'{level}_id'] if lower_unit else False
                if ancestor and ancestor != unit:
                    user[f'home_{lower}_id'] = False
            user._clear_unset_org_scope_level()

    @api.onchange('home_division_id')
    def _onchange_home_division_id(self):
        self._org_home_changed('division')

    @api.onchange('home_business_unit_id')
    def _onchange_home_business_unit_id(self):
        self._org_home_changed('business_unit')

    @api.onchange('home_location_id')
    def _onchange_home_location_id(self):
        self._org_home_changed('location')

    @api.onchange('home_department_id')
    def _onchange_home_department_id(self):
        self._org_home_changed('department')

    def _clear_unset_org_scope_level(self):
        """Untick 'scope all apps' when the home unit for that level is empty."""
        for user in self:
            if user.org_scope_level and not user[f'home_{user.org_scope_level}_id']:
                user.org_scope_level = False

    @api.constrains('home_division_id', 'home_business_unit_id',
                    'home_location_id', 'home_department_id', 'org_scope_level')
    def _check_home_org_units(self):
        config = self.env['org.config']
        for user in self:
            for index, level in enumerate(ORG_LEVELS):
                unit = user[f'home_{level}_id']
                if not unit:
                    continue
                for higher in ORG_LEVELS[:index]:
                    ancestor = unit[f'{higher}_id']
                    if ancestor and user[f'home_{higher}_id'] and ancestor != user[f'home_{higher}_id']:
                        raise ValidationError(_(
                            "%(user)s: the Home %(lower)s doesn't sit under the Home %(higher)s.",
                            user=user.display_name, lower=config._label(level),
                            higher=config._label(higher)))
            if user.org_scope_level and not user[f'home_{user.org_scope_level}_id']:
                raise ValidationError(_(
                    "%(user)s: set the Home %(level)s before scoping all apps to it.",
                    user=user.display_name,
                    level=config._label(user.org_scope_level)))

    # ------------------------------------------------------------------
    # Record scoping
    # ------------------------------------------------------------------

    def _get_org_scope_domain(self, model_name):
        """Domain limiting ``model_name`` records for this user, or None.

        The "scope all apps" level, when ticked, applies to every model and
        overrides App Specific Scoping. Otherwise App Specific Scoping for
        any app that opens the model applies (several matching apps add up).
        Records with no Organisation units at all stay visible to everyone.
        """
        self.ensure_one()
        domains = []
        if self.org_scope_level:
            level = self.org_scope_level
            domains.append(Domain(f'org_{level}_id', '=', self[f'home_{level}_id'].id))
        else:
            for line in self.org_app_scope_ids:
                line_domain = line._get_record_domain()
                if line_domain is not None and model_name in line._get_app_models():
                    domains.append(line_domain)
        if not domains:
            return None
        unassigned = Domain.AND(Domain(f'org_{level}_id', '=', False) for level in ORG_LEVELS)
        return Domain.OR(domains) | unassigned

    def _org_sync_partner(self):
        """A user's contact sits in the user's home units (rather than those
        of whoever created the user)."""
        if 'org_division_id' not in self.env['res.partner']._fields:
            return
        for user in self:
            user.partner_id.sudo().write({
                f'org_{level}_id': user[f'home_{level}_id'].id for level in ORG_LEVELS
            })

    # Record rules are cached per user: drop the cache when scoping changes.
    @api.model_create_multi
    def create(self, vals_list):
        org_changed = any(
            field in vals for vals in vals_list
            for field in ORG_FIELDS + tuple(f'org_scope_{level}' for level in ORG_LEVELS))
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            flags = self._pop_org_scope_flags(vals)
            if flags and 'org_scope_level' not in vals:
                vals['org_scope_level'] = self._org_scope_level_from_flags(False, flags)
        users = super().create(vals_list)
        self.env['res.users.org.scope']._sync_app_lines(users)
        users._org_sync_partner()
        if org_changed:
            self.env.registry.clear_cache()
        return users

    def write(self, vals):
        # The checkboxes only drive org_scope_level, which is what gets stored.
        org_changed = any(field in vals for field in ORG_FIELDS) or any(
            f'org_scope_{level}' in vals for level in ORG_LEVELS)
        vals = dict(vals)
        flags = self._pop_org_scope_flags(vals)
        if flags and 'org_scope_level' not in vals:
            res = True
            for user in self:
                level = self._org_scope_level_from_flags(user.org_scope_level, flags)
                res &= super(ResUsers, user).write(dict(vals, org_scope_level=level))
        else:
            res = super().write(vals)
        if 'group_ids' in vals:
            # Portal users turned internal now need their app list.
            self.env['res.users.org.scope']._sync_app_lines(self)
        if any(f'home_{level}_id' in vals for level in ORG_LEVELS):
            self._org_sync_partner()
        if org_changed:
            self.env.registry.clear_cache()
        return res

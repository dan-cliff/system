from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

from .org_scope_mixin import ORG_LEVELS

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

    @api.onchange('home_division_id')
    def _onchange_home_division_id(self):
        for user in self:
            if user.home_business_unit_id.division_id != user.home_division_id:
                user.home_business_unit_id = False
            user._clear_unset_org_scope_level()

    @api.onchange('home_business_unit_id')
    def _onchange_home_business_unit_id(self):
        for user in self:
            if user.home_business_unit_id:
                user.home_division_id = user.home_business_unit_id.division_id
            if user.home_location_id.business_unit_id != user.home_business_unit_id:
                user.home_location_id = False
            user._clear_unset_org_scope_level()

    @api.onchange('home_location_id')
    def _onchange_home_location_id(self):
        for user in self:
            if user.home_location_id:
                user.home_business_unit_id = user.home_location_id.business_unit_id
                user.home_division_id = user.home_location_id.division_id
            if user.home_department_id.location_id != user.home_location_id:
                user.home_department_id = False
            user._clear_unset_org_scope_level()

    @api.onchange('home_department_id')
    def _onchange_home_department_id(self):
        for user in self:
            if user.home_department_id:
                user.home_location_id = user.home_department_id.location_id
                user.home_business_unit_id = user.home_department_id.business_unit_id
                user.home_division_id = user.home_department_id.division_id
            user._clear_unset_org_scope_level()

    def _clear_unset_org_scope_level(self):
        """Untick 'scope all apps' when the home unit for that level is empty."""
        for user in self:
            if user.org_scope_level and not user[f'home_{user.org_scope_level}_id']:
                user.org_scope_level = False

    @api.constrains('home_division_id', 'home_business_unit_id',
                    'home_location_id', 'home_department_id', 'org_scope_level')
    def _check_home_org_units(self):
        for user in self:
            bu, loc, dept = user.home_business_unit_id, user.home_location_id, user.home_department_id
            if (bu and bu.division_id != user.home_division_id
                    or loc and loc.business_unit_id != bu
                    or dept and dept.location_id != loc):
                raise ValidationError(_(
                    "%(user)s: the Home Department, Location, Business Unit and Division "
                    "must sit under each other.", user=user.display_name))
            if user.org_scope_level and not user[f'home_{user.org_scope_level}_id']:
                raise ValidationError(_(
                    "%(user)s: set the Home %(level)s before scoping all apps to it.",
                    user=user.display_name,
                    level=LEVEL_LABELS[user.org_scope_level]))

    # ------------------------------------------------------------------
    # Record scoping
    # ------------------------------------------------------------------

    def _get_org_scope_domain(self, model_name):
        """Domain limiting ``model_name`` records for this user, or None.

        App Specific Scoping for any app that opens the model takes
        precedence (several matching apps add up); otherwise the
        "scope all apps" level applies. Records with no Division stay
        visible to everyone.
        """
        self.ensure_one()
        domains = []
        for line in self.org_app_scope_ids:
            line_domain = line._get_record_domain()
            if line_domain is not None and model_name in line._get_app_models():
                domains.append(line_domain)
        if not domains and self.org_scope_level:
            level = self.org_scope_level
            domains.append(Domain(f'org_{level}_id', '=', self[f'home_{level}_id'].id))
        if not domains:
            return None
        return Domain.OR(domains) | Domain('org_division_id', '=', False)

    # Record rules are cached per user: drop the cache when scoping changes.
    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            flags = self._pop_org_scope_flags(vals)
            if flags and 'org_scope_level' not in vals:
                vals['org_scope_level'] = self._org_scope_level_from_flags(False, flags)
        users = super().create(vals_list)
        self.env['res.users.org.scope']._sync_app_lines(users)
        if any(field in vals for vals in vals_list for field in ORG_FIELDS):
            self.env.registry.clear_cache()
        return users

    def write(self, vals):
        # The checkboxes only drive org_scope_level, which is what gets stored.
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
        if any(field in vals for field in ORG_FIELDS):
            self.env.registry.clear_cache()
        return res

from odoo import api, fields, models

ORG_LEVELS = ('division', 'business_unit', 'location', 'department')
ORG_FIELD_NAMES = tuple(f'org_{level}_id' for level in ORG_LEVELS)
ORG_SHOW_FIELD_NAMES = tuple(f'org_show_{level}' for level in ORG_LEVELS)
ORG_LEVEL_MODELS = {
    'division': 'org.division',
    'business_unit': 'org.business.unit',
    'location': 'org.location',
    'department': 'org.department',
}


def org_scope_fields():
    """Fresh field instances for the Organisation fields.

    Used by ``org.scope.mixin`` and by the automatic injection on primary
    models (see ``ir_model_fields.py``), so both always match.
    """
    return {
        'org_division_id': fields.Many2one(
            comodel_name='org.division',
            string='Division',
            index=True,
            ondelete='restrict',
            compute='_compute_org_division_id',
            store=True,
            readonly=False,
            precompute=True,
        ),
        'org_business_unit_id': fields.Many2one(
            comodel_name='org.business.unit',
            string='Business Unit',
            index=True,
            ondelete='restrict',
            domain="[('division_id', '=?', org_division_id)]",
            compute='_compute_org_business_unit_id',
            store=True,
            readonly=False,
            precompute=True,
        ),
        'org_location_id': fields.Many2one(
            comodel_name='org.location',
            string='Location',
            index=True,
            ondelete='restrict',
            domain="[('division_id', '=?', org_division_id),"
                   " '|', ('business_unit_id', '=', False), ('business_unit_id', '=?', org_business_unit_id)]",
            compute='_compute_org_location_id',
            store=True,
            readonly=False,
            precompute=True,
        ),
        'org_department_id': fields.Many2one(
            comodel_name='org.department',
            string='Department',
            index=True,
            ondelete='restrict',
            domain="[('division_id', '=?', org_division_id),"
                   " '|', ('business_unit_id', '=', False), ('business_unit_id', '=?', org_business_unit_id),"
                   " '|', ('location_id', '=', False), ('location_id', '=?', org_location_id)]",
        ),
        # Whether each level has any units at all, so forms only show the
        # Organisation fields once the structure has been set up.
        'org_show_division': fields.Boolean(compute='_compute_org_show'),
        'org_show_business_unit': fields.Boolean(compute='_compute_org_show'),
        'org_show_location': fields.Boolean(compute='_compute_org_show'),
        'org_show_department': fields.Boolean(compute='_compute_org_show'),
    }


_FIELDS = org_scope_fields()


class OrgScopeMixin(models.AbstractModel):
    """Link records to the organisation hierarchy so they can be scoped.

    Primary models of every installed app get these fields automatically
    (see ``ir_model_fields.py``); inherit this mixin to add them explicitly.
    Setting a lower level fills in every level above it; changing a higher
    level clears the levels below that no longer belong to it. Records with
    no Organisation units at all are not restricted by scoping.

    A record created from a parent record (e.g. a Feed for an Animal) copies
    the parent's Organisation values; set ``_org_parent_field`` to name the
    parent's Many2one when the automatic choice (the first required
    Many2one to another Organisation-aware model) isn't right, or to False
    to turn it off.
    """
    _name = 'org.scope.mixin'
    _description = 'Organisation Scope Mixin'

    # Read by ir.rule._compute_domain to decide which models get scoped.
    _org_scoped = True

    org_division_id = _FIELDS['org_division_id']
    org_business_unit_id = _FIELDS['org_business_unit_id']
    org_location_id = _FIELDS['org_location_id']
    org_department_id = _FIELDS['org_department_id']
    org_show_division = _FIELDS['org_show_division']
    org_show_business_unit = _FIELDS['org_show_business_unit']
    org_show_location = _FIELDS['org_show_location']
    org_show_department = _FIELDS['org_show_department']

    # Each level comes from the lowest unit set below it (units store all
    # their ancestors); with no unit below, it keeps its own value.
    @api.depends('org_department_id.location_id')
    def _compute_org_location_id(self):
        for rec in self:
            if rec.org_department_id:
                rec.org_location_id = rec.org_department_id.location_id
            else:
                rec.org_location_id = rec.org_location_id

    @api.depends('org_location_id.business_unit_id', 'org_department_id.business_unit_id')
    def _compute_org_business_unit_id(self):
        for rec in self:
            if rec.org_location_id:
                rec.org_business_unit_id = rec.org_location_id.business_unit_id
            elif rec.org_department_id:
                rec.org_business_unit_id = rec.org_department_id.business_unit_id
            else:
                rec.org_business_unit_id = rec.org_business_unit_id

    @api.depends('org_business_unit_id.division_id', 'org_location_id.division_id',
                 'org_department_id.division_id')
    def _compute_org_division_id(self):
        for rec in self:
            lower = rec.org_business_unit_id or rec.org_location_id or rec.org_department_id
            if lower:
                rec.org_division_id = lower.division_id
            else:
                rec.org_division_id = rec.org_division_id

    def _compute_org_show(self):
        config = self.env['org.config']
        shown = {
            level: config._is_enabled(level) and bool(self.env[model].search_count([], limit=1))
            for level, model in ORG_LEVEL_MODELS.items()
        }
        for rec in self:
            for level in ORG_LEVELS:
                rec[f'org_show_{level}'] = shown[level]

    def _org_clear_lower_levels(self, level):
        """After ``level`` changed, drop lower units that sit under another
        unit at that level (or under any, when it was cleared)."""
        value = self[f'org_{level}_id']
        for lower in ORG_LEVELS[ORG_LEVELS.index(level) + 1:]:
            unit = self[f'org_{lower}_id']
            ancestor = unit[f'{level}_id'] if unit else False
            if ancestor and ancestor != value:
                self[f'org_{lower}_id'] = False

    @api.onchange('org_division_id')
    def _onchange_org_division_id(self):
        for rec in self:
            rec._org_clear_lower_levels('division')

    @api.onchange('org_business_unit_id')
    def _onchange_org_business_unit_id(self):
        for rec in self:
            rec._org_clear_lower_levels('business_unit')

    @api.onchange('org_location_id')
    def _onchange_org_location_id(self):
        for rec in self:
            rec._org_clear_lower_levels('location')


# Methods copied onto models that get the fields injected automatically.
ORG_SCOPE_METHODS = (
    '_compute_org_location_id',
    '_compute_org_business_unit_id',
    '_compute_org_division_id',
    '_compute_org_show',
    '_onchange_org_division_id',
    '_onchange_org_business_unit_id',
    '_onchange_org_location_id',
    '_org_clear_lower_levels',
)

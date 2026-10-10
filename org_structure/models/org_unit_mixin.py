from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .org_scope_mixin import ORG_LEVELS


class OrgUnitMixin(models.AbstractModel):
    """Shared behaviour of Business Units, Locations and Departments.

    Each unit stores a link to every level above it. Which of those is the
    real parent (editable and required) is set in Settings › Organisational
    Management; the levels above the parent are derived from it, and levels
    between the parent and the unit stay empty.
    """
    _name = 'org.unit.mixin'
    _description = 'Organisation Unit'

    # Set on each model: the level its records belong to.
    _org_level = None

    org_parent_level = fields.Char(
        compute='_compute_org_parent_level',
        help='Technical: the level this unit hangs under (Settings › Organisational Management).',
    )

    def _compute_org_parent_level(self):
        parent = self.env['org.config']._parent_level(self._org_level) or False
        for rec in self:
            rec.org_parent_level = parent

    def _org_parent_link_fields(self):
        index = ORG_LEVELS.index(self._org_level)
        return ['name'] + [f'{level}_id' for level in ORG_LEVELS[:index]]

    @api.constrains(lambda self: self._org_parent_link_fields())
    def _check_org_parent(self):
        config = self.env['org.config']
        parent = config._parent_level(self._org_level)
        if not parent:
            return
        for rec in self:
            if not rec[f'{parent}_id']:
                raise ValidationError(self.env._(
                    "%(unit)s: set its %(parent)s.",
                    unit=rec.display_name, parent=config._label(parent),
                ))

    def _org_company_from_links(self):
        """The company of the nearest linked unit above, if any."""
        self.ensure_one()
        index = ORG_LEVELS.index(self._org_level)
        for level in reversed(ORG_LEVELS[:index]):
            unit = self[f'{level}_id']
            if unit:
                return unit.company_id
        return self.env['res.company']

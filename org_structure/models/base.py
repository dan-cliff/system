from lxml import etree

from odoo import api, models

from .org_scope_mixin import ORG_FIELD_NAMES, ORG_LEVEL_MODELS, ORG_LEVELS


class Base(models.AbstractModel):
    _inherit = 'base'

    def _org_is_scoped(self):
        return bool(getattr(type(self), '_org_scoped', False)) and 'org_division_id' in self._fields

    def _org_parent_field_name(self):
        """The Many2one to the parent record whose Organisation a new record
        copies, or False. ``_org_parent_field`` on the model wins; otherwise
        a Many2one to another Organisation-aware model that is either
        required or the inverse of that model's One2many (e.g. a Task's
        Project), required ones first."""
        cache = getattr(self.pool, '_org_parent_fields', None)
        if cache is None:
            cache = self.pool._org_parent_fields = {}
        if self._name not in cache:
            name = getattr(type(self), '_org_parent_field', None)
            if name is None:
                candidates = [
                    field for field in self._fields.values()
                    if field.type == 'many2one' and field.store
                    and field.comodel_name != self._name
                    and field.name not in ORG_FIELD_NAMES
                    and self.env[field.comodel_name]._org_is_scoped()
                ]
                required = [field for field in candidates if field.required]
                inverse = [
                    field for field in candidates
                    if any(
                        other.type == 'one2many' and other.comodel_name == self._name
                        and other.inverse_name == field.name
                        for other in self.env[field.comodel_name]._fields.values()
                    )
                ]
                name = (required or inverse or [None])[0]
                name = name.name if name else False
            cache[self._name] = name
        return cache[self._name]

    def _org_values_from_parent(self, parent_id):
        """The parent's four Organisation values (all False when it has none,
        so the child stays unassigned like its parent)."""
        parent_field = self._org_parent_field_name()
        parent = self.env[self._fields[parent_field].comodel_name].sudo().browse(parent_id).exists()
        if not parent:
            return {}
        return {name: parent[name].id for name in ORG_FIELD_NAMES}

    def _org_values_from_user(self):
        """The logged-in user's Home Division / Business Unit / Location /
        Department, or nothing when no home is set."""
        user = self.env.user
        if not user.home_division_id:
            return {}
        return {f'org_{level}_id': user[f'home_{level}_id'].id for level in ORG_LEVELS}

    # New records take their Organisation from the parent they are created
    # from (e.g. a Feed for an Enclosure); otherwise from the logged-in
    # user's home units. Values given explicitly always win.
    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if not self._org_is_scoped() or any(res.get(name) for name in ORG_FIELD_NAMES):
            return res
        parent_field = self._org_parent_field_name()
        parent_id = parent_field and res.get(parent_field)
        values = self._org_values_from_parent(parent_id) if parent_id else self._org_values_from_user()
        res.update({name: value for name, value in values.items() if name in fields})
        return res

    @api.model_create_multi
    def create(self, vals_list):
        if self._org_is_scoped():
            parent_field = self._org_parent_field_name()
            for vals in vals_list:
                if any(vals.get(name) for name in ORG_FIELD_NAMES):
                    self._org_complete_values(vals)
                elif parent_field and vals.get(parent_field):
                    # Explicit (possibly empty) values, so the user's home
                    # units don't override the parent's through default_get.
                    vals.update(self._org_values_from_parent(vals[parent_field]))
        return super().create(vals_list)

    def _org_complete_values(self, vals):
        """Fill the levels missing from ``vals`` from the units given: levels
        above the lowest given unit come from it, levels below stay empty.
        This keeps default_get (the user's home units) from mixing in."""
        units = {
            level: self.env[model].browse(vals[f'org_{level}_id'])
            for level, model in ORG_LEVEL_MODELS.items() if vals.get(f'org_{level}_id')
        }
        lowest = [level for level in ORG_LEVELS if level in units][-1]
        unit = units[lowest]
        # org units store all their parents, e.g. a department's division_id
        above = ORG_LEVELS[:ORG_LEVELS.index(lowest)]
        for level in ORG_LEVELS:
            name = f'org_{level}_id'
            if name not in vals:
                vals[name] = unit[f'{level}_id'].id if level in above else False

    # Forms of Organisation-aware models get an Organisation section, shown
    # only for the levels that have units.
    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if (view_type == 'form' and 'org_show_division' in self._fields
                and not arch.xpath("//field[@name='org_division_id']")):
            self._org_add_form_section(arch)
        return arch, view

    @api.model
    def _org_add_form_section(self, arch):
        group = etree.Element('group', {
            'name': 'org_structure',
            'string': self.env._('Organisation'),
            'invisible': 'not org_show_division',
        })
        for level in ORG_LEVELS:
            etree.SubElement(group, 'field', {'name': f'org_show_{level}', 'invisible': '1'})
        for level in ORG_LEVELS:
            etree.SubElement(group, 'field', {
                'name': f'org_{level}_id',
                'invisible': f'not org_show_{level}',
                'options': "{'no_create': True}",
            })
        container = next(iter(arch.xpath('./sheet')), arch)
        notebook = next(iter(container.xpath('./notebook')), None)
        if notebook is not None:
            notebook.addprevious(group)
        else:
            container.append(group)

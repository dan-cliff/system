import logging

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# How a column shows. A technical selection: _apply_to_arch() depends on the
# values, so it isn't an option model (see CLAUDE.md > Choice fields).
VISIBILITY = [
    ('show', 'Always Shown'),
    ('optional_show', 'Optional, Shown'),
    ('optional_hide', 'Optional, Hidden'),
    ('hidden', 'Hidden'),
]
# Field types that can't be shown as a list column.
UNLISTABLE_TYPES = ('binary', 'one2many', 'html', 'properties', 'properties_definition', 'json')
TRUE_VALUES = ('1', 'True', 'true')


def is_technical_column(node):
    """A column the view always hides (kept only for its value)."""
    return node.get('column_invisible') in TRUE_VALUES


class ListColumnConfig(models.Model):
    """The column layout of one list view, applied for every user."""
    _name = 'list.column.config'
    _description = 'List Column Layout'
    _order = 'model, id'

    name = fields.Char(string='List', compute='_compute_name', store=True)
    model = fields.Char(string='Model', required=True, index=True)
    model_name = fields.Char(string='Records', compute='_compute_name', store=True)
    view_id = fields.Many2one(
        comodel_name='ir.ui.view',
        string='List View',
        ondelete='cascade',
        domain="[('type', '=', 'list'), ('model', '=', model)]",
        help='Empty for the list Odoo generates for models without a list view.',
    )
    app_id = fields.Many2one(
        comodel_name='list.column.app',
        string='Last Changed In',
        ondelete='set null',
        readonly=True,
    )
    line_ids = fields.One2many(
        comodel_name='list.column.config.line',
        inverse_name='config_id',
        string='Columns',
        copy=True,
    )
    line_count = fields.Integer(string='Column Count', compute='_compute_line_count')
    active = fields.Boolean(default=True)

    @api.constrains('model', 'view_id', 'active')
    def _check_one_per_view(self):
        for config in self:
            if self.with_context(active_test=False).search_count([
                ('id', '!=', config.id), ('model', '=', config.model),
                ('view_id', '=', config.view_id.id),
            ]):
                raise ValidationError(self.env._('This list view already has a column layout.'))

    @api.depends('model', 'view_id')
    def _compute_name(self):
        for config in self:
            model = self.env['ir.model']._get(config.model) if config.model else False
            config.model_name = model.name if model else config.model
            config.name = config.view_id.name or config.model_name

    @api.depends('line_ids')
    def _compute_line_count(self):
        for config in self:
            config.line_count = len(config.line_ids)

    @api.model
    def _get_for_view(self, model, view_id):
        return self.sudo().search([('model', '=', model), ('view_id', '=', view_id or False)], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        configs = super().create(vals_list)
        self.env['list.column.app']._views_changed()
        return configs

    def write(self, vals):
        res = super().write(vals)
        self.env['list.column.app']._views_changed()
        return res

    def unlink(self):
        res = super().unlink()
        self.env['list.column.app']._views_changed()
        return res

    # ── Applying the layout ───────────────────────────────────────────────

    def _apply_to_arch(self, arch, model):
        """Reorder, show, hide, relabel and add the list's columns in place.

        Columns are never removed (other columns' modifiers may read them):
        hidden ones get column_invisible. Columns the view always hides, and
        columns with no line (e.g. added by a module installed since), are
        left where they are. Fields the model no longer has are skipped."""
        self.ensure_one()
        if arch.tag != 'list':
            return
        model_fields = model._fields
        columns = {}
        for node in arch:
            if node.tag == 'field' and not is_technical_column(node):
                columns.setdefault(node.get('name'), node)

        ordered = []
        for line in self.line_ids.sorted(lambda l: (l.sequence, l.id)):
            field = model_fields.get(line.field_name)
            if not field:
                continue
            node = columns.pop(line.field_name, None)
            if node is None:
                if field.type in UNLISTABLE_TYPES or any(n is not None and n.get('name') == line.field_name for n, _line in ordered):
                    continue
                node = self._new_column(arch, model, field)
            ordered.append((node, line))

        # The configured columns take the places the view's own ones had, in
        # the configured order; added columns go after the last of them.
        placed = {id(node) for node, _line in ordered}
        slots = []
        for node in list(arch):
            if id(node) in placed:
                slot = etree.Comment('list_column_config')
                node.addprevious(slot)
                slots.append(slot)
                arch.remove(node)
        anchor = None
        for index, (node, line) in enumerate(ordered):
            if index < len(slots):
                slots[index].addprevious(node)
            elif anchor is not None:
                anchor.addnext(node)
            else:
                fields_ = [n for n in arch if n.tag == 'field']
                if fields_:
                    fields_[-1].addnext(node)
                else:
                    arch.append(node)
            anchor = node
            self._apply_line(node, line)
        for slot in slots:
            arch.remove(slot)

    @api.model
    def _new_column(self, arch, model, field):
        node = etree.Element('field', {'name': field.name})
        if field.type == 'many2many':
            node.set('widget', 'many2many_tags')
        elif field.type in ('date', 'datetime'):
            node.set('options', "{'numeric': True}")
        elif field.type == 'monetary':
            currency_field = field.get_currency_field(model)
            if currency_field and currency_field in model._fields and not arch.xpath(
                    "./field[@name=$name]", name=currency_field):
                etree.SubElement(arch, 'field', {'name': currency_field, 'column_invisible': '1'})
        return node

    @api.model
    def _apply_line(self, node, line):
        node.attrib.pop('optional', None)
        if line.visibility == 'optional_show':
            node.set('optional', 'show')
        elif line.visibility == 'optional_hide':
            node.set('optional', 'hide')
        elif line.visibility == 'hidden':
            node.set('column_invisible', '1')
        if line.label:
            node.set('string', line.label)


class ListColumnConfigLine(models.Model):
    _name = 'list.column.config.line'
    _description = 'List Column'
    _order = 'sequence, id'

    config_id = fields.Many2one(
        comodel_name='list.column.config',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(default=10)
    field_name = fields.Char(string='Field', required=True)
    label = fields.Char(string='Column Heading', help='Leave empty to keep the heading the list gives it.')
    visibility = fields.Selection(VISIBILITY, string='Shown', required=True, default='show')
    is_added = fields.Boolean(string='Added', help='Not one of the list view\'s own columns.')

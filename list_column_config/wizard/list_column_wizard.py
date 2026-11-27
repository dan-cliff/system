from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from ..models.list_column_config import UNLISTABLE_TYPES, VISIBILITY, is_technical_column


class ListColumnWizard(models.TransientModel):
    _name = 'list.column.wizard'
    _description = 'Customise List Columns'

    res_model = fields.Char(string='Model', required=True, readonly=True)
    model_name = fields.Char(string='Records', readonly=True)
    view_id = fields.Many2one('ir.ui.view', string='List View', readonly=True)
    app_id = fields.Many2one('list.column.app', string='App', readonly=True)
    app_name = fields.Char(string='App Name', readonly=True)
    has_layout = fields.Boolean(readonly=True)
    field_option_ids = fields.One2many(
        comodel_name='list.column.wizard.field',
        inverse_name='wizard_id',
        string='Fields',
    )
    line_ids = fields.One2many(
        comodel_name='list.column.wizard.line',
        inverse_name='wizard_id',
        string='Columns',
    )

    # ── Opening ───────────────────────────────────────────────────────────

    @api.model
    def action_open_wizard(self, res_model, view_id=False, menu_id=False):
        """Called by the list views' "Customise columns" icon: check the user
        may customise lists in the app, then open the wizard with the list's
        current columns."""
        if res_model not in self.env:
            raise UserError(self.env._('Unknown model %s.', res_model))
        app = self.env['list.column.app']._get_app(menu_id)
        if not app._user_can_customise():
            raise AccessError(self.env._(
                'You are not allowed to customise the columns of the lists in %s.', app.name))
        model = self.env[res_model]
        view = self.env['ir.ui.view'].sudo().browse(view_id).exists() if view_id else self.env['ir.ui.view']
        if view and (view.model != res_model or view.type != 'list'):
            raise UserError(self.env._('This is not a list view of %s.', res_model))
        config = self.env['list.column.config']._get_for_view(res_model, view.id)
        wizard = self.create({
            'res_model': res_model,
            'model_name': self.env['ir.model'].sudo()._get(res_model).name,
            'view_id': view.id,
            'app_id': app.id,
            'app_name': app.name,
            'has_layout': bool(config),
        })
        columns = self._column_values(model, view, config)
        wizard.field_option_ids = [
            (0, 0, vals) for vals in self._field_option_values(model, [vals['field_name'] for vals in columns])
        ]
        options = {option.name: option.id for option in wizard.field_option_ids}
        wizard.line_ids = [
            (0, 0, {key: value for key, value in vals.items() if key != 'field_name'}
             | {'field_option_id': options[vals['field_name']]})
            for vals in columns
            if vals['field_name'] in options
        ]
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Customise Columns: %s', wizard.model_name),
            'res_model': self._name,
            'res_id': wizard.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

    @api.model
    def _column_values(self, model, view, config):
        """The wizard lines: the saved layout's columns in its order, then the
        view's columns that have no line yet, in the view's order."""
        arch, _view = model.sudo().with_context(list_column_config_original=True)._get_view(
            view.id or None, 'list')
        columns = {}
        for node in arch:
            if node.tag == 'field' and not is_technical_column(node) and node.get('name') in model._fields:
                columns.setdefault(node.get('name'), node)

        values = []
        for line in config.line_ids:
            field = model._fields.get(line.field_name)
            node = columns.pop(line.field_name, None)
            if not field or (node is None and field.type in UNLISTABLE_TYPES):
                continue
            values.append(self._line_values(
                model, line.field_name, node, visibility=line.visibility, label=line.label or ''))
        for name, node in columns.items():
            values.append(self._line_values(model, name, node))
        for sequence, vals in enumerate(values, start=1):
            vals['sequence'] = sequence * 10
        return values

    @api.model
    def _field_option_values(self, model, column_names):
        """The list's own columns, and the fields that can be added: those
        the user may see and that a list can show."""
        descriptions = model.fields_get(attributes=['string', 'type'])
        values = []
        for name, field in model._fields.items():
            in_view = name in column_names
            addable = name in descriptions and field.type not in UNLISTABLE_TYPES
            if in_view or addable:
                label = descriptions[name]['string'] if name in descriptions else field.string
                values.append({'name': name, 'label': label or name, 'ttype': field.type, 'addable': addable})
        return values

    @api.model
    def _line_values(self, model, name, node, visibility=None, label=''):
        default_label = (node.get('string') if node is not None else '') or model._fields[name].string
        if visibility is None:
            visibility = {'show': 'optional_show', 'hide': 'optional_hide'}.get(node.get('optional'), 'show')
        return {
            'field_name': name,
            'in_view': node is not None,
            'default_label': default_label,
            'label': label,
            'visibility': visibility,
        }

    # ── Saving ────────────────────────────────────────────────────────────

    def _check_can_customise(self):
        self.ensure_one()
        if not self.app_id.sudo()._user_can_customise():
            raise AccessError(self.env._(
                'You are not allowed to customise the columns of the lists in %s.', self.app_name))

    def action_save(self):
        self._check_can_customise()
        model = self.env[self.res_model]
        names = set()
        lines = []
        for line in self.line_ids.sorted(lambda l: (l.sequence, l.id)):
            option = line.field_option_id
            name = option.name
            if option.wizard_id != self or name not in model._fields:
                raise UserError(self.env._('%s is not a field of these records.', option.label))
            if not line.in_view and model._fields[name].type in UNLISTABLE_TYPES:
                raise UserError(self.env._('%s cannot be shown as a list column.', option.label))
            if name in names:
                raise UserError(self.env._('%s is listed more than once.', option.label))
            names.add(name)
            label = (line.label or '').strip()
            lines.append((0, 0, {
                'sequence': len(lines) + 1,
                'field_name': name,
                'label': label if label != line.default_label else False,
                'visibility': line.visibility,
                'is_added': not line.in_view,
            }))
        Config = self.env['list.column.config'].sudo()
        config = Config._get_for_view(self.res_model, self.view_id.id)
        values = {'app_id': self.app_id.id, 'line_ids': [(5, 0, 0)] + lines}
        if config:
            config.write(values)
        else:
            Config.create(dict(values, model=self.res_model, view_id=self.view_id.id))
        return self._close()

    def action_reset(self):
        """Back to the columns the list view itself defines."""
        self._check_can_customise()
        self.env['list.column.config']._get_for_view(self.res_model, self.view_id.id).unlink()
        return self._close()

    def _close(self):
        version = self.env['ir.config_parameter'].sudo().get_param('list_column_config.version', 0)
        return {
            'type': 'ir.actions.act_window_close',
            'infos': {'list_column_saved': True, 'version': int(version or 0)},
        }


class ListColumnWizardLine(models.TransientModel):
    _name = 'list.column.wizard.line'
    _description = 'Customise List Columns: Column'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('list.column.wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(default=1000)
    field_option_id = fields.Many2one(
        comodel_name='list.column.wizard.field',
        string='Field',
        required=True,
        ondelete='cascade',
        domain="[('wizard_id', '=', parent.id), ('addable', '=', True)]",
    )
    field_name = fields.Char(related='field_option_id.name', string='Technical Name')
    in_view = fields.Boolean(string='In List View', readonly=True)
    default_label = fields.Char(string='Default Heading', readonly=True)
    label = fields.Char(string='Column Heading', help='Leave empty to keep the default heading.')
    visibility = fields.Selection(VISIBILITY, string='Shown', required=True, default='show')

    @api.onchange('field_option_id')
    def _onchange_field_option_id(self):
        if not self.in_view:
            self.default_label = self.field_option_id.label


class ListColumnWizardField(models.TransientModel):
    """A field the wizard's columns can show (the user may not read
    ir.model.fields)."""
    _name = 'list.column.wizard.field'
    _description = 'Customise List Columns: Field'
    _rec_name = 'label'
    _order = 'label'

    wizard_id = fields.Many2one('list.column.wizard', required=True, ondelete='cascade')
    name = fields.Char(string='Technical Name', required=True)
    label = fields.Char(string='Field', required=True)
    ttype = fields.Char(string='Type')
    addable = fields.Boolean()

    @api.depends('label', 'name')
    def _compute_display_name(self):
        for option in self:
            option.display_name = f'{option.label} ({option.name})'

    @api.model
    def _search_display_name(self, operator, value):
        if operator in ('ilike', 'not ilike') and value:
            domain = ['|', ('label', 'ilike', value), ('name', 'ilike', value)]
            return ['!', *domain] if operator == 'not ilike' else domain
        return super()._search_display_name(operator, value)

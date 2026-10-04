import datetime
import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.safe_eval import datetime as safe_datetime, dateutil, safe_eval, time

_logger = logging.getLogger(__name__)

GROUPABLE_TYPES = ('char', 'selection', 'many2one', 'boolean', 'date', 'datetime', 'integer')
MEASURE_TYPES = ('integer', 'float', 'monetary')
DATE_TYPES = ('date', 'datetime')
# Upper bound on groups/points sent to the browser for one widget.
MAX_GROUPS = 500
MAX_POINTS = 2000

# Technical choices passed straight to the ORM (_read_group), so they stay
# fixed selections rather than configurable option models.
AGGREGATES = [
    ('sum', 'Sum'),
    ('avg', 'Average'),
    ('min', 'Minimum'),
    ('max', 'Maximum'),
    ('count_distinct', 'Count distinct'),
]
INTERVALS = [
    ('day', 'Day'),
    ('week', 'Week'),
    ('month', 'Month'),
    ('quarter', 'Quarter'),
    ('year', 'Year'),
]
ELAPSED_UNITS = [
    ('day', 'Days'),
    ('week', 'Weeks'),
    ('month', 'Months'),
    ('year', 'Years'),
]
VALUE_MODES = [
    ('aggregate', 'Aggregate a measure'),
    ('elapsed', 'Time since the latest date'),
]
MAP_LEVELS = [
    ('country', 'Countries'),
    ('state', 'States / provinces'),
    ('point', 'Contact locations'),
]
# Contact locations are rounded to about 1 km so a public map never
# pinpoints an address.
MAP_POINT_PRECISION = 2
# Records read when a map's address path can only be followed in Python.
MAP_MAX_RECORDS = 20000
# Odoo's own six-colour chart palette, used when no default colours are set.
BUILTIN_COLORS = ['#4EA7F2', '#EA6175', '#43C5B1', '#F4A261', '#8481DD', '#FFD86D']
# Odoo's colour-index palette ($o-colors): index 1-11 of an Integer "color"
# field such as a tag colour. 0 means no colour.
INDEX_COLORS = ['', '#ee2d2d', '#dc8534', '#e8bb1d', '#5794dd', '#9f628f', '#db8865',
                '#41a9a2', '#304be0', '#ee2f8a', '#61c36e', '#9872e6']
RECORD_COLOR_TYPES = ('char', 'integer')
COLOR_FIELDS = ['color', 'color_2', 'color_3', 'color_4', 'color_5', 'color_6']
AXIS_SORTS = [
    ('sequence', 'Sequence'),
    ('sequence_desc', 'Sequence (reversed)'),
    ('label', 'Name'),
    ('value_desc', 'Largest first'),
    ('value_asc', 'Smallest first'),
]
PERIOD_STEPS = {
    'day': relativedelta(days=1),
    'week': relativedelta(weeks=1),
    'month': relativedelta(months=1),
    'quarter': relativedelta(months=3),
    'year': relativedelta(years=1),
}
# Technical: each scope is a lookup in code (see _user_scope_ids).
USER_SCOPES = [
    ('self', 'Self'),
    ('manager', 'Manager'),
    ('team', 'My Team'),
    ('extended_team', 'My Extended Team'),
]
USER_FILTER_MODELS = ('res.users', 'hr.employee')


class CustomDashboardWidget(models.Model):
    _name = 'custom.dashboard.widget'
    _description = 'Dashboard Widget'
    _order = 'dashboard_id, pos_y, pos_x, id'

    name = fields.Char(string='Title', required=True, translate=True)
    subtitle = fields.Char(string='Subtitle', translate=True)
    dashboard_id = fields.Many2one(
        'custom.dashboard', string='Dashboard', required=True, ondelete='cascade', index=True,
    )
    type_id = fields.Many2one(
        'custom.dashboard.widget.type', string='Widget Type', required=True, ondelete='restrict',
    )
    type_code = fields.Char(related='type_id.code', string='Renderer Code')
    data_mode = fields.Selection(related='type_id.data_mode', string='Data Mode')
    supports_series = fields.Boolean(related='type_id.supports_series')
    requires_series = fields.Boolean(related='type_id.requires_series')
    uses_second_measure = fields.Boolean(related='type_id.uses_second_measure')

    # Layout on the 12-column grid
    pos_x = fields.Integer(string='Column', default=0)
    pos_y = fields.Integer(string='Row', default=0)
    width = fields.Integer(string='Width', default=4)
    height = fields.Integer(string='Height', default=4)

    # Data source
    model_id = fields.Many2one(
        'ir.model', string='Model', ondelete='cascade',
        domain=[('transient', '=', False), ('abstract', '=', False)],
    )
    model_name = fields.Char(related='model_id.model', string='Model Name')
    domain = fields.Char(string='Filter', default='[]')
    user_filter_scope = fields.Selection(
        USER_SCOPES, string='Only Records Of',
        help='Limit the records by who they belong to, relative to the person viewing the dashboard '
             '(on public website pages, the "Show Data As" user):\n'
             '- Self: the viewer\n'
             '- Manager: the viewer\'s manager\n'
             '- My Team: people whose manager is the viewer\n'
             '- My Extended Team: the viewer and everyone below them in the hierarchy\n'
             'Managers come from the Employees app.',
    )
    user_filter_path = fields.Char(
        string='User Field',
        help='The user or employee on the record to check, e.g. Responsible User or Employee. '
             'Leave empty when the model is Users or Employees.',
    )
    groupby_field_id = fields.Many2one(
        'ir.model.fields', string='Group By', ondelete='set null',
        domain="[('model_id', '=', model_id), ('store', '=', True), ('ttype', 'in', %s)]" % (list(GROUPABLE_TYPES),),
    )
    groupby_field_type = fields.Selection(related='groupby_field_id.ttype', string='Group By Type')
    groupby_interval = fields.Selection(INTERVALS, string='Group By Interval', default='month')
    series_field_id = fields.Many2one(
        'ir.model.fields', string='Split Series By', ondelete='set null',
        domain="[('model_id', '=', model_id), ('store', '=', True), ('ttype', 'in', %s)]" % (list(GROUPABLE_TYPES),),
    )
    series_field_type = fields.Selection(related='series_field_id.ttype', string='Series Type')
    groupby_relation = fields.Char(related='groupby_field_id.relation', string='Group By Model')
    series_relation = fields.Char(related='series_field_id.relation', string='Series Model')
    groupby_color_field_id = fields.Many2one(
        'ir.model.fields', string='Group Colours From', ondelete='set null',
        domain="[('model', '=', groupby_relation), ('ttype', 'in', %s)]" % (list(RECORD_COLOR_TYPES),),
        help='Colour each group with the colour stored on its record, e.g. the colour of a risk '
             'rating. Works with hex colour fields (#d9534f) and colour-index fields. Groups '
             'without a colour use the widget colours.',
    )
    series_color_field_id = fields.Many2one(
        'ir.model.fields', string='Series Colours From', ondelete='set null',
        domain="[('model', '=', series_relation), ('ttype', 'in', %s)]" % (list(RECORD_COLOR_TYPES),),
        help='Colour each series with the colour stored on its record. Series without a colour '
             'use the widget colours.',
    )
    series_interval = fields.Selection(INTERVALS, string='Series Interval', default='year')
    measure_field_id = fields.Many2one(
        'ir.model.fields', string='Measure', ondelete='set null',
        domain="[('model_id', '=', model_id), ('store', '=', True), ('ttype', 'in', %s)]" % (list(MEASURE_TYPES),),
        help='Leave empty to count records.',
    )
    aggregate = fields.Selection(AGGREGATES, string='Aggregate', default='sum')
    measure2_field_id = fields.Many2one(
        'ir.model.fields', string='Second Measure', ondelete='set null',
        domain="[('model_id', '=', model_id), ('store', '=', True), ('ttype', 'in', %s)]" % (list(MEASURE_TYPES),),
        help='Leave empty to count records.',
    )
    aggregate2 = fields.Selection(AGGREGATES, string='Second Aggregate', default='sum')
    limit = fields.Integer(string='Limit', default=0, help='Show only the first N groups. 0 shows all.')

    # Group and series ordering, used by every grouped widget (pivot tables included).
    pivot_row_sort = fields.Selection(
        AXIS_SORTS, string='Sort Groups By', default='sequence', required=True,
        help='Sequence follows the field\'s own order: the linked records\' order, the order of the '
             'selection options, Yes before No, or oldest date first. Sequence (reversed) is the '
             'opposite, e.g. newest date first.',
    )
    pivot_col_sort = fields.Selection(AXIS_SORTS, string='Sort Series By', default='sequence', required=True)

    # Pivot table axes
    pivot_show_all_rows = fields.Boolean(
        string='Show All Groups',
        help='List every possible group value, even those without records: all options of a '
             'selection, all records of a linked model, Yes and No, or every period between the '
             'first and last date.',
    )
    pivot_show_all_columns = fields.Boolean(string='Show All Series', help='Same as Show All Groups, for the columns.')
    pivot_row_label = fields.Char(string='Group Label', translate=True,
                                  help='Shown alongside the rows, e.g. "Department".')
    pivot_col_label = fields.Char(string='Series Label', translate=True,
                                  help='Shown above the columns, e.g. "Injury type".')
    pivot_hide_none_rows = fields.Boolean(
        string='Hide "None" Group', help='Leave out the row of records with no value for the group field.')
    pivot_hide_none_columns = fields.Boolean(
        string='Hide "None" Series', help='Leave out the column of records with no value for the series field.')
    pivot_hide_row_totals = fields.Boolean(
        string='Hide Group Totals', help='Hide the Total column that adds up each group across the series.')
    pivot_hide_column_totals = fields.Boolean(
        string='Hide Series Totals', help='Hide the Total row that adds up each series across the groups.')

    # Display
    custom_colors = fields.Boolean(
        string='Custom Colours',
        help='Use this widget\'s own colours instead of the default colours from Settings.',
    )
    color = fields.Char(string='Colour 1')
    color_2 = fields.Char(string='Colour 2')
    color_3 = fields.Char(string='Colour 3')
    color_4 = fields.Char(string='Colour 4')
    color_5 = fields.Char(string='Colour 5')
    color_6 = fields.Char(string='Colour 6')
    colors_preview = fields.Html(
        string='Colours', compute='_compute_colors_preview', sanitize=False,
        help='Charts cycle through these colours in order, repeating them when there are more series or slices.',
    )
    show_legend = fields.Boolean(string='Show Legend', default=True)
    show_values = fields.Boolean(string='Show Values')
    show_border = fields.Boolean(string='Show Border', default=True, help='Draw a thin border around the widget.')
    show_shadow = fields.Boolean(string='Show Drop Shadow', help='Lift the widget off the page with a soft shadow.')
    decimals = fields.Integer(string='Decimals', default=0)
    prefix = fields.Char(string='Prefix', help='Shown before values, e.g. $.')
    suffix = fields.Char(string='Suffix', help='Shown after values, e.g. kg.')
    # Single-value widgets (KPI, gauge)
    value_mode = fields.Selection(
        VALUE_MODES, string='Value', default='aggregate', required=True,
        help='Aggregate a measure over the found records, or count the time '
             'since the latest date among them (e.g. days since the last incident).',
    )
    elapsed_field_id = fields.Many2one(
        'ir.model.fields', string='Date Field', ondelete='set null',
        domain="[('model_id', '=', model_id), ('store', '=', True), ('ttype', 'in', %s)]" % (list(DATE_TYPES),),
        help='The latest value of this field among the found records is the starting point.',
    )
    elapsed_unit = fields.Selection(ELAPSED_UNITS, string='Count In', default='day', required=True)
    # Map widgets
    map_address_path = fields.Char(
        string='Address From',
        help='Path from the record to the contact whose address places it on the map, '
             'e.g. Customer or Employee > Work Contact. Leave empty when the model is Contacts.',
    )
    map_level = fields.Selection(
        MAP_LEVELS, string='Show', default='country', required=True,
        help='Shade countries or states by value, or plot each contact location as a bubble '
             '(needs contacts with map coordinates).',
    )
    map_country_id = fields.Many2one(
        'res.country', string='Zoom to Country',
        help='Only count records in this country and zoom the map to it.',
    )
    map_state_id = fields.Many2one(
        'res.country.state', string='Zoom to State',
        domain="[('country_id', '=?', map_country_id)]",
        help='Only count records in this state and zoom the map to it.',
    )
    target_value = fields.Float(string='Target')
    gauge_min = fields.Float(string='Gauge Minimum', default=0.0)
    gauge_max = fields.Float(string='Gauge Maximum', default=100.0)
    text_content = fields.Html(string='Text', sanitize=True)
    image = fields.Image(string='Image', max_width=1920, max_height=1920)

    @api.onchange('groupby_field_id', 'series_field_id')
    def _onchange_color_source(self):
        for widget in self:
            if widget.groupby_color_field_id.model != widget.groupby_field_id.relation:
                widget.groupby_color_field_id = False
            if widget.series_color_field_id.model != widget.series_field_id.relation:
                widget.series_color_field_id = False

    @api.onchange('model_id')
    def _onchange_model_id(self):
        for widget in self:
            model = widget.model_id
            for fname in ('groupby_field_id', 'series_field_id', 'measure_field_id', 'measure2_field_id', 'elapsed_field_id'):
                if widget[fname] and widget[fname].model_id != model:
                    widget[fname] = False
            if widget._origin.model_id != model:
                if widget.domain and widget.domain != '[]':
                    widget.domain = '[]'
                widget.map_address_path = False
                widget.user_filter_path = False

    @api.constrains('model_id', 'groupby_field_id', 'series_field_id', 'measure_field_id', 'measure2_field_id',
                    'elapsed_field_id')
    def _check_fields_model(self):
        for widget in self:
            for fname in ('groupby_field_id', 'series_field_id', 'measure_field_id', 'measure2_field_id',
                          'elapsed_field_id'):
                field = widget[fname]
                if field and field.model_id != widget.model_id:
                    raise ValidationError(_(
                        'Field "%(field)s" does not belong to model "%(model)s".',
                        field=field.field_description, model=widget.model_id.name or '',
                    ))

    @api.constrains('width', 'height')
    def _check_size(self):
        for widget in self:
            if not 1 <= widget.width <= 12 or widget.height < 1:
                raise ValidationError(_('Widgets must be 1-12 columns wide and at least 1 row high.'))

    # ------------------------------------------------------------------
    # Front-end API
    # ------------------------------------------------------------------
    def _get_config(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'subtitle': self.subtitle or '',
            'type': self.type_code,
            'data_mode': self.data_mode,
            'x': self.pos_x,
            'y': self.pos_y,
            'w': self.width,
            'h': self.height,
            'colors': self._get_colors(),
            'color': (self._get_colors() or [''])[0],
            'show_legend': self.show_legend,
            'show_values': self.show_values,
            'show_border': self.show_border,
            'show_shadow': self.show_shadow,
            'decimals': max(self.decimals, 0),
            'prefix': self.prefix or '',
            'suffix': self.suffix or '',
            'target': self.target_value,
            'value_mode': self.value_mode,
            'elapsed_unit': self.elapsed_unit,
            'gauge_min': self.gauge_min,
            'gauge_max': self.gauge_max,
            'measure_label': self._measure_label(self.measure_field_id, self.aggregate),
            'measure2_label': self._measure_label(self.measure2_field_id, self.aggregate2),
            'groupby_label': self.groupby_field_id.field_description or '',
            'series_label': self.series_field_id.field_description or '',
            'x_label': self.measure_field_id.field_description or _('Count'),
            'y_label': self.measure2_field_id.field_description or _('Count'),
            'text_content': self.text_content or '',
            'pivot_row_label': self.pivot_row_label or '',
            'pivot_col_label': self.pivot_col_label or '',
            'pivot_row_totals': not self.pivot_hide_row_totals,
            'pivot_column_totals': not self.pivot_hide_column_totals,
            'map_level': self.map_level,
            'map_country_code': self.map_country_id.code or self.map_state_id.country_id.code or '',
            'map_state_key': self._map_state_key(self.map_state_id),
            'map_state_name': self.map_state_id.name or '',
            'image_url': (
                '/web/image/custom.dashboard.widget/%s/image?unique=%s'
                % (self.id, int(self.write_date.timestamp()) if self.write_date else 0)
            ) if self.image else '',
        }

    def get_config(self):
        return [widget._get_config() for widget in self]

    def get_widget_data(self):
        """Return ``{widget_id: data}`` for each widget, computed as the
        current user so their access rights and record rules apply."""
        return self._get_widget_data(self.env)

    def _get_widget_data(self, data_env):
        """Return ``{widget_id: data}`` with the data read through
        ``data_env``, whose user's access rights and record rules apply."""
        result = {}
        for widget in self:
            try:
                result[widget.id] = widget._compute_data(data_env)
            except (AccessError, UserError, ValidationError) as error:
                result[widget.id] = {'error': str(error.args[0] if error.args else error)}
            except Exception:
                _logger.exception('Custom dashboard widget %s failed to load data', widget.id)
                result[widget.id] = {'error': _('This widget could not load its data. Check its configuration.')}
        return result

    def remove_widget(self):
        self.mapped('dashboard_id')._check_can_edit()
        self.unlink()
        return True

    def duplicate_widget(self):
        self.ensure_one()
        self.dashboard_id._check_can_edit()
        new = self.copy({'pos_y': self.pos_y + self.height})
        return new._get_config()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    @api.model
    def _measure_label(self, field, aggregate):
        if not field:
            return _('Count')
        agg = dict(self._fields['aggregate']._description_selection(self.env)).get(aggregate, '')
        return '%s (%s)' % (field.field_description, agg) if agg else field.field_description

    def _compute_data(self, data_env=None):
        self.ensure_one()
        data_env = data_env if data_env is not None else self.env
        if self.data_mode == 'content':
            return {}
        if not self.model_id:
            return {'error': _('Choose a model for this widget.')}
        if self.model_name not in data_env:
            return {'error': _('Model "%s" is not available.', self.model_name)}
        Model = data_env[self.model_name]
        domain = self._get_domain(data_env) + self._user_filter_domain(Model)
        if self.data_mode == 'single':
            return self._compute_single(Model, domain)
        if self.data_mode == 'map':
            return self._compute_map(Model, domain)
        if self.data_mode == 'points':
            return self._compute_points(Model, domain)
        return self._compute_grouped(Model, domain)

    def _get_domain(self, data_env=None):
        if not self.domain:
            return []
        data_env = data_env if data_env is not None else self.env
        today = fields.Date.context_today(self.with_env(data_env))
        eval_context = {
            **data_env['ir.rule']._eval_context(),
            'uid': data_env.uid,
            'datetime': safe_datetime,
            'relativedelta': dateutil.relativedelta.relativedelta,
            'context_today': lambda: today,
            'time': time,
        }
        try:
            domain = safe_eval(self.domain, eval_context)
        except Exception as error:
            raise UserError(_('The filter of widget "%(name)s" is not valid: %(error)s', name=self.name, error=error))
        if not isinstance(domain, (list, tuple)):
            raise UserError(_('The filter of widget "%s" is not a list.', self.name))
        return list(domain)

    def _user_filter_domain(self, Model):
        """Domain limiting records to the chosen user relationship."""
        if not self.user_filter_scope:
            return []
        path = (self.user_filter_path or '').strip()
        target = Model._name
        for name in path.split('.') if path else []:
            field = self.env[target]._fields.get(name)
            if not field or field.type != 'many2one':
                raise UserError(_('"%s" is not a path of single links to a user or employee.', path))
            target = field.comodel_name
        if target not in USER_FILTER_MODELS:
            if not path:
                raise UserError(_('Choose the user or employee field to filter on.'))
            raise UserError(_('"%s" must lead to a user or an employee.', path))
        ids = self._user_scope_ids(Model.env, target)
        return [(path or 'id', 'in', ids)]

    def _user_scope_ids(self, env, target):
        """Ids of ``target`` (users or employees) in the widget's scope,
        relative to ``env``'s user. Managers come from the Employees app."""
        scope = self.user_filter_scope
        uid = env.uid
        if 'hr.employee' not in env:
            if scope == 'self' and target == 'res.users':
                return [uid]
            raise UserError(_('Manager and team filters need the Employees app.'))
        # The hierarchy is read with sudo: only ids leave this method, and
        # the records themselves are still read with the viewer's rights.
        Employee = env['hr.employee'].sudo()
        mine = Employee.search([('user_id', '=', uid)])
        if scope == 'self':
            employees = mine
        elif scope == 'manager':
            employees = mine.parent_id
        elif scope == 'team':
            employees = Employee.search([('parent_id', 'in', mine.ids)]) if mine else Employee
        else:
            employees = Employee.search([('id', 'child_of', mine.ids)]) if mine else Employee
        if target == 'hr.employee':
            return employees.ids
        user_ids = set(employees.user_id.ids)
        if scope in ('self', 'extended_team'):
            # The viewer's own records always count, even without an employee.
            user_ids.add(uid)
        return sorted(user_ids)

    @api.model
    def _aggregate_spec(self, field, aggregate):
        if not field:
            return '__count'
        return '%s:%s' % (field.name, aggregate or 'sum')

    @api.model
    def _groupby_spec(self, field, interval):
        if field.ttype in DATE_TYPES:
            return '%s:%s' % (field.name, interval or 'month')
        return field.name

    def _check_field(self, Model, field):
        if field and field.name not in Model._fields:
            raise UserError(_('Field "%s" no longer exists on this model.', field.name))

    def _compute_single(self, Model, domain):
        if self.value_mode == 'elapsed':
            return self._compute_elapsed(Model, domain)
        self._check_field(Model, self.measure_field_id)
        spec = self._aggregate_spec(self.measure_field_id, self.aggregate)
        rows = Model._read_group(domain, [], [spec])
        value = rows[0][0] if rows else 0
        return {'value': float(value or 0)}

    def _compute_elapsed(self, Model, domain):
        """Whole days/weeks/months/years from the latest date to today.

        Negative when the latest date is in the future. ``value`` is None
        when no found record has a date.
        """
        field = self.elapsed_field_id
        if not field:
            return {'error': _('Choose the date field to count from.')}
        self._check_field(Model, field)
        rows = Model._read_group(domain, [], ['%s:max' % field.name])
        latest = rows[0][0] if rows else False
        if not latest:
            return {'value': None, 'latest': False}
        if isinstance(latest, datetime.datetime):
            # Compare calendar days in the reading user's timezone.
            latest = fields.Datetime.context_timestamp(Model, latest).date()
        today = fields.Date.context_today(Model)
        return {
            'value': self._elapsed_between(latest, today, self.elapsed_unit),
            'latest': latest.strftime('%d/%m/%Y'),
        }

    @api.model
    def _elapsed_between(self, start, end, unit):
        """Whole ``unit``s from ``start`` to ``end`` (negative if ``end`` is earlier)."""
        if unit in ('day', 'week'):
            days = (end - start).days
            weeks = abs(days) // 7
            return float(days if unit == 'day' else (weeks if days >= 0 else -weeks))
        delta = relativedelta(end, start)
        if unit == 'month':
            return float(delta.years * 12 + delta.months)
        return float(delta.years)

    @api.model
    def _get_default_colors(self):
        """Default colours from Settings, in order, skipping empty slots."""
        params = self.env['ir.config_parameter'].sudo()
        colors = [params.get_param('custom_dashboard.default_color_%d' % i) for i in range(1, 7)]
        return [c for c in colors if c]

    def _get_colors(self):
        """Colours the widget cycles through; empty means Odoo's chart palette."""
        self.ensure_one()
        if self.custom_colors:
            colors = [self[fname] for fname in COLOR_FIELDS if self[fname]]
            if colors:
                return colors
        return self._get_default_colors()

    @api.depends('custom_colors', *COLOR_FIELDS)
    def _compute_colors_preview(self):
        defaults = None
        for widget in self:
            colors = [widget[f] for f in COLOR_FIELDS if widget[f]] if widget.custom_colors else []
            if not colors:
                if defaults is None:
                    defaults = self._get_default_colors() or BUILTIN_COLORS
                colors = defaults
            swatches = ''.join(
                '<span class="d-inline-block rounded me-1" title="%s" '
                'style="width:22px;height:22px;background:%s;border:1px solid rgba(0,0,0,.15)"></span>'
                % (color, color) for color in colors if self._is_hex_color(color)
            )
            widget.colors_preview = '<div class="d-flex">%s</div>' % swatches

    @api.model
    def _is_hex_color(self, value):
        value = (value or '').lstrip('#')
        return len(value) in (3, 6, 8) and all(c in '0123456789abcdefABCDEF' for c in value)

    @api.onchange('custom_colors')
    def _onchange_custom_colors(self):
        """Start custom colours from the current defaults."""
        for widget in self:
            if widget.custom_colors and not any(widget[f] for f in COLOR_FIELDS):
                for fname, color in zip(COLOR_FIELDS, self._get_default_colors() or BUILTIN_COLORS):
                    widget[fname] = color

    @api.constrains(*COLOR_FIELDS)
    def _check_colors(self):
        for widget in self:
            for fname in COLOR_FIELDS:
                if widget[fname] and not self._is_hex_color(widget[fname]):
                    raise ValidationError(_('"%s" is not a colour.', widget[fname]))

    @api.onchange('map_state_id')
    def _onchange_map_state_id(self):
        if self.map_state_id:
            self.map_country_id = self.map_state_id.country_id

    @api.model
    def _map_state_key(self, state):
        """ISO 3166-2 style key (e.g. AU-VIC) used to match state shapes."""
        if not state:
            return ''
        return '%s-%s' % (state.country_id.code or '', state.code or '')

    def _map_partner_path(self, Model):
        """Validate ``map_address_path`` and return it ('' for contacts)."""
        path = (self.map_address_path or '').strip()
        if not path:
            if Model._name == 'res.partner':
                return ''
            raise UserError(_('Choose which contact\'s address places each record on the map.'))
        current = Model
        for name in path.split('.'):
            field = current._fields.get(name)
            if not field or field.type != 'many2one':
                raise UserError(_('"%s" is not a path of single links to a contact.', path))
            current = self.env[field.comodel_name]
        if current._name != 'res.partner':
            raise UserError(_('"%s" must lead to a contact (it leads to %s).', path, current._description))
        return path

    def _compute_map(self, Model, domain):
        path = self._map_partner_path(Model)
        self._check_field(Model, self.measure_field_id)
        aggregates = [self._aggregate_spec(self.measure_field_id, self.aggregate), '__count']

        if self.map_level == 'point':
            return self._compute_map_points(Model, domain, path, aggregates)

        target = 'state_id' if self.map_level == 'state' else 'country_id'
        regions = []
        unlocated = 0
        for group, value, count in self._map_read_group(Model, domain, path, target, aggregates, MAX_GROUPS):
            if not group:
                unlocated += count
                continue
            group = group.sudo()
            if self.map_level == 'state':
                key, country = self._map_state_key(group), group.country_id.code or ''
            else:
                key, country = group.code or '', group.code or ''
            regions.append({
                'key': key,
                'name': group.display_name if self.map_level == 'country' else group.name,
                'country': country,
                'value': float(value or 0),
                'count': count,
            })
        return {'regions': regions, 'unlocated': unlocated}

    def _map_read_group(self, Model, domain, path, target, aggregates, limit):
        """``[(group, value, count)]`` with records grouped by the contact at
        ``path`` (or its ``target`` field, e.g. country_id).

        The database groups the records when every step of the path is a
        stored field. Paths through computed fields (e.g. an employee's
        User Partner) can't be grouped in SQL, so those records are read
        and grouped here instead.
        """
        steps = path.split('.') if path else []
        current, stored = Model, True
        for name in steps:
            field = current._fields[name]
            stored = stored and field.store
            current = Model.env[field.comodel_name]
        # Zoom to Country / State also limits the records counted.
        focus_field, focus = (
            ('state_id', self.map_state_id) if self.map_state_id
            else ('country_id', self.map_country_id) if self.map_country_id
            else (None, None)
        )
        if stored:
            if focus:
                domain = domain + [('.'.join(steps + [focus_field]), '=', focus.id)]
            groupby = '.'.join(steps + [target]) if target else (path or 'id')
            return Model._read_group(domain, [groupby], aggregates, limit=limit)

        measure = self.measure_field_id.name if self.measure_field_id else None
        records = Model.search_fetch(domain, [measure] if measure else [], limit=MAP_MAX_RECORDS)
        buckets = {}
        for record in records:
            group = record
            for name in steps:
                group = group[name]
            if focus and group[focus_field] != focus:
                continue
            if target:
                group = group[target]
            bucket = buckets.setdefault(group.id, [group, []])
            bucket[1].append(record[measure] if measure else None)
        result = [
            (group, self._aggregate_values(values), len(values))
            for group, values in buckets.values()
        ]
        return result[:limit]

    def _aggregate_values(self, values):
        """Python version of the widget's SQL aggregate (empty values skipped)."""
        if not self.measure_field_id:
            return float(len(values))
        present = [v for v in values if v is not False and v is not None]
        if self.aggregate == 'count_distinct':
            return float(len(set(present)))
        if not present:
            return 0.0
        if self.aggregate == 'avg':
            return float(sum(present)) / len(present)
        if self.aggregate == 'min':
            return float(min(present))
        if self.aggregate == 'max':
            return float(max(present))
        return float(sum(present))

    def _compute_map_points(self, Model, domain, path, aggregates):
        Partner = Model.env['res.partner']
        if 'partner_latitude' not in Partner._fields:
            return {'error': _('Contact locations need the Partners Geolocation app (base_geolocalize).')}
        rows = self._map_read_group(Model, domain, path, None, aggregates, MAX_POINTS)
        # Contacts the reader may not open are left off the map.
        partners = Partner.browse([row[0].id for row in rows if row[0]])._filtered_access('read')
        coords = {
            rec['id']: rec for rec in partners.read(['partner_latitude', 'partner_longitude', 'city'])
        } if partners else {}
        cells = {}
        unlocated = 0
        for partner, value, count in rows:
            rec = coords.get(partner.id) if partner else None
            lat, lng = (rec['partner_latitude'], rec['partner_longitude']) if rec else (0.0, 0.0)
            if not rec or (not lat and not lng):
                unlocated += count
                continue
            key = (round(lat, MAP_POINT_PRECISION), round(lng, MAP_POINT_PRECISION))
            cell = cells.setdefault(key, {'lat': key[0], 'lng': key[1], 'value': 0.0, 'count': 0, 'cities': set()})
            cell['value'] += float(value or 0)
            cell['count'] += count
            if rec['city']:
                cell['cities'].add(rec['city'])
        points = []
        for cell in cells.values():
            cities = sorted(cell.pop('cities'))
            cell['name'] = ', '.join(cities[:3]) or _('Unknown place')
            points.append(cell)
        return {'points': points, 'unlocated': unlocated}

    def _compute_points(self, Model, domain):
        x_field, y_field = self.measure_field_id, self.measure2_field_id
        if not x_field or not y_field:
            return {'error': _('Choose an X measure and a Y measure.')}
        self._check_field(Model, x_field)
        self._check_field(Model, y_field)
        limit = min(self.limit or MAX_POINTS, MAX_POINTS)
        records = Model.search_fetch(domain, [x_field.name, y_field.name], limit=limit)
        points = [
            {'x': float(rec[x_field.name] or 0), 'y': float(rec[y_field.name] or 0), 'label': rec.display_name}
            for rec in records
        ]
        return {'points': points}

    def _compute_grouped(self, Model, domain):
        group_field = self.groupby_field_id
        if not group_field:
            return {'error': _('Choose a field to group by.')}
        series_field = self.series_field_id if self.supports_series else self.env['ir.model.fields']
        if self.requires_series and not series_field:
            return {'error': _('Choose a field to split the series by.')}
        for field in (group_field, series_field, self.measure_field_id, self.measure2_field_id):
            self._check_field(Model, field)

        groupby = [self._groupby_spec(group_field, self.groupby_interval)]
        if series_field:
            groupby.append(self._groupby_spec(series_field, self.series_interval))
        aggregates = [self._aggregate_spec(self.measure_field_id, self.aggregate)]
        if self.uses_second_measure:
            aggregates.append(self._aggregate_spec(self.measure2_field_id, self.aggregate2))
        aggregates.append('__count')

        rows = Model._read_group(domain, groupby, aggregates, limit=MAX_GROUPS * (20 if series_field else 1))

        # Collect the primary groups, keeping the raw value for ordering.
        groups = {}
        series = {}
        cells = {}
        for row in rows:
            key = self._group_key(row[0])
            groups.setdefault(key, {'raw': row[0], 'value': 0.0, 'value2': 0.0, 'count': 0})
            values = row[len(groupby):]
            value = float(values[0] or 0)
            value2 = float(values[1] or 0) if self.uses_second_measure else 0.0
            count = values[-1] or 0
            group = groups[key]
            group['value'] += value
            group['value2'] += value2
            group['count'] += count
            if series_field:
                skey = self._group_key(row[1])
                series.setdefault(skey, row[1])
                cells[(key, skey)] = cells.get((key, skey), 0.0) + value

        is_pivot = self.type_code == 'pivot'
        if is_pivot and self.pivot_show_all_rows:
            existing = [g['raw'] for g in groups.values()]
            for raw in self._all_group_values(Model, group_field, self.groupby_interval, existing):
                groups.setdefault(self._group_key(raw), {'raw': raw, 'value': 0.0, 'value2': 0.0, 'count': 0})
        if is_pivot and series_field and self.pivot_show_all_columns:
            for raw in self._all_group_values(Model, series_field, self.series_interval, list(series.values())):
                series.setdefault(self._group_key(raw), raw)
        if is_pivot and self.pivot_hide_none_rows:
            groups = {k: g for k, g in groups.items() if not self._is_none_group(group_field, g['raw'])}
        if is_pivot and series_field and self.pivot_hide_none_columns:
            series = {k: raw for k, raw in series.items() if not self._is_none_group(series_field, raw)}

        keys = self._sort_axis(
            Model, group_field, self.groupby_interval, self.pivot_row_sort, list(groups),
            lambda k: groups[k]['raw'], lambda k: groups[k]['value'],
        )
        limit = min(self.limit or MAX_GROUPS, MAX_GROUPS)
        keys = keys[:limit]

        labels = [self._format_group(group_field, self.groupby_interval, groups[k]['raw']) for k in keys]
        data = {
            'labels': labels,
            'values': [groups[k]['value'] for k in keys],
            'counts': [groups[k]['count'] for k in keys],
        }
        group_colors = self._record_colors(group_field, self.groupby_color_field_id, [groups[k]['raw'] for k in keys])
        if group_colors:
            data['colors'] = group_colors
        if self.uses_second_measure:
            data['values2'] = [groups[k]['value2'] for k in keys]
        if series_field:
            series_keys = self._sort_axis(
                Model, series_field, self.series_interval, self.pivot_col_sort, list(series),
                lambda s: series[s], lambda s: sum(cells.get((k, s), 0.0) for k in groups),
            )
            series_colors = self._record_colors(
                series_field, self.series_color_field_id, [series[s] for s in series_keys],
            ) or [None] * len(series_keys)
            data['series'] = [
                {
                    'label': self._format_group(series_field, self.series_interval, series[s]),
                    'values': [cells.get((k, s), 0.0) for k in keys],
                    'color': color,
                }
                for s, color in zip(series_keys, series_colors)
            ]
        return data

    @api.model
    def _record_colors(self, group_field, color_field, raws):
        """Colour of each grouped record, read from ``color_field`` on the
        records ``group_field`` links to; None when none of them has one."""
        if not color_field or group_field.ttype != 'many2one' or color_field.model != group_field.relation:
            return None
        colors = [self._record_color(raw, color_field.name) for raw in raws]
        return colors if any(colors) else None

    @api.model
    def _record_color(self, record, fname):
        """A CSS colour for ``record``'s ``fname`` value, or None."""
        if not record or not isinstance(record, models.BaseModel) or fname not in record._fields:
            return None
        value = record.sudo()[fname]
        if record._fields[fname].type == 'integer':
            if value and 0 < value < len(INDEX_COLORS):
                return INDEX_COLORS[value]
            return None
        value = (value or '').strip()
        if not self._is_hex_color(value):
            return None
        digits = value.lstrip('#').lower()
        if len(digits) == 3:
            digits = ''.join(c * 2 for c in digits)
        return '#' + digits[:6]

    def _all_group_values(self, Model, field, interval, existing):
        """Every value ``field`` could be grouped by, for pivot tables that
        list empty rows or columns too. Fields with open-ended values (text,
        numbers) only list the values that occur."""
        model_field = Model._fields[field.name]
        if field.ttype == 'selection':
            return [value for value, _label in model_field._description_selection(self.env)]
        if field.ttype == 'boolean':
            return [True, False]
        if field.ttype == 'many2one':
            # Read in the data environment, so access rules apply.
            return list(Model.env[model_field.comodel_name].search([], limit=MAX_GROUPS))
        if field.ttype in DATE_TYPES:
            periods = sorted(v for v in existing if v)
            if not periods:
                return []
            step, current, values = PERIOD_STEPS.get(interval or 'month'), periods[0], []
            while current <= periods[-1] and len(values) < MAX_GROUPS:
                values.append(current)
                current += step
            return values
        return []

    @api.model
    def _is_none_group(self, field, raw):
        """Whether ``raw`` is the "None" group (no value). False is "No" for booleans."""
        if field.ttype == 'boolean':
            return raw is None
        if field.ttype == 'integer':
            return raw is None or raw is False
        return not raw

    def _sort_axis(self, Model, field, interval, order, keys, raw_of, value_of):
        """Order group or series ``keys`` by ``order`` (see AXIS_SORTS); empty groups last."""
        def empty(key):
            return self._is_none_group(field, raw_of(key))

        if order == 'label':
            def label_key(key):
                return (empty(key), self._format_group(field, interval, raw_of(key)).casefold())
            return sorted(keys, key=label_key)
        sequence_key = self._sequence_key(Model, field, [raw_of(k) for k in keys])
        ordered = sorted(keys, key=lambda k: (empty(k), sequence_key(raw_of(k))))
        if order == 'sequence_desc':
            # Reverse the order but keep empty groups at the end.
            filled = [k for k in ordered if not empty(k)]
            return filled[::-1] + [k for k in ordered if empty(k)]
        if order in ('value_desc', 'value_asc'):
            # Stable sort: equal values keep their sequence order.
            ordered.sort(key=value_of, reverse=order == 'value_desc')
        return ordered

    def _sequence_key(self, Model, field, raws):
        """Key giving the field's natural order for the given raw values."""
        if field.ttype == 'many2one':
            records = [raw for raw in raws if isinstance(raw, models.BaseModel) and raw]
            if records:
                comodel = records[0].sudo().with_context(active_test=False)
                ordered = comodel.search([('id', 'in', [r.id for r in records])])
                rank = {record.id: index for index, record in enumerate(ordered)}
            else:
                rank = {}
            return lambda raw: rank.get(raw.id, len(rank)) if raw else len(rank)
        if field.ttype == 'selection':
            options = [v for v, _l in Model._fields[field.name]._description_selection(self.env)]
            return lambda raw: options.index(raw) if raw in options else len(options)
        if field.ttype == 'boolean':
            return lambda raw: 0 if raw else 1
        return self._sort_key

    @api.model
    def _group_key(self, value):
        if isinstance(value, models.BaseModel):
            return (value._name, value.id)
        return value

    @api.model
    def _sort_key(self, value):
        """Order groups naturally, with empty values last."""
        if isinstance(value, models.BaseModel):
            return (not value, (value.sudo().display_name or '').lower())
        if value is False or value is None:
            return (True, '')
        if isinstance(value, datetime.datetime):
            return (False, value.isoformat())
        if isinstance(value, datetime.date):
            return (False, datetime.datetime.combine(value, datetime.time()).isoformat())
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return (False, '%020.6f' % value)
        return (False, str(value).lower())

    def _format_group(self, field, interval, value):
        if isinstance(value, models.BaseModel):
            # Same as the ORM's grouped views: names of the related records
            # are shown even if the user cannot open them.
            return value.sudo().display_name if value else _('None')
        if field.ttype == 'boolean':
            return _('Yes') if value else _('No')
        if value is False or value is None:
            return _('None')
        if field.ttype in DATE_TYPES:
            return self._format_period(value, interval)
        if field.ttype == 'selection':
            Model = self.env[field.model]
            selection = dict(Model._fields[field.name]._description_selection(self.env))
            return selection.get(value, str(value))
        return str(value)

    @api.model
    def _format_period(self, value, interval):
        if isinstance(value, str):
            value = fields.Datetime.to_datetime(value)
        if interval == 'year':
            return value.strftime('%Y')
        if interval == 'quarter':
            return 'Q%s %s' % ((value.month - 1) // 3 + 1, value.strftime('%Y'))
        if interval == 'month':
            return value.strftime('%m/%Y')
        return value.strftime('%d/%m/%Y')

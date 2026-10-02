import datetime
import logging

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
SORTS = [
    ('label', 'Group order'),
    ('value_desc', 'Largest first'),
    ('value_asc', 'Smallest first'),
]


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
    sort = fields.Selection(SORTS, string='Sort', default='label', required=True)
    limit = fields.Integer(string='Limit', default=0, help='Show only the first N groups. 0 shows all.')

    # Display
    color = fields.Char(string='Colour', help='Hex colour for single-series charts. Empty uses the palette.')
    show_legend = fields.Boolean(string='Show Legend', default=True)
    show_values = fields.Boolean(string='Show Values')
    decimals = fields.Integer(string='Decimals', default=0)
    prefix = fields.Char(string='Prefix', help='Shown before values, e.g. $.')
    suffix = fields.Char(string='Suffix', help='Shown after values, e.g. kg.')
    target_value = fields.Float(string='Target')
    gauge_min = fields.Float(string='Gauge Minimum', default=0.0)
    gauge_max = fields.Float(string='Gauge Maximum', default=100.0)
    text_content = fields.Html(string='Text', sanitize=True)
    image = fields.Image(string='Image', max_width=1920, max_height=1920)

    @api.onchange('model_id')
    def _onchange_model_id(self):
        for widget in self:
            model = widget.model_id
            for fname in ('groupby_field_id', 'series_field_id', 'measure_field_id', 'measure2_field_id'):
                if widget[fname] and widget[fname].model_id != model:
                    widget[fname] = False
            if widget.domain and widget.domain != '[]' and widget._origin.model_id != model:
                widget.domain = '[]'

    @api.constrains('model_id', 'groupby_field_id', 'series_field_id', 'measure_field_id', 'measure2_field_id')
    def _check_fields_model(self):
        for widget in self:
            for fname in ('groupby_field_id', 'series_field_id', 'measure_field_id', 'measure2_field_id'):
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
            'color': self.color or '',
            'show_legend': self.show_legend,
            'show_values': self.show_values,
            'decimals': max(self.decimals, 0),
            'prefix': self.prefix or '',
            'suffix': self.suffix or '',
            'target': self.target_value,
            'gauge_min': self.gauge_min,
            'gauge_max': self.gauge_max,
            'measure_label': self._measure_label(self.measure_field_id, self.aggregate),
            'measure2_label': self._measure_label(self.measure2_field_id, self.aggregate2),
            'groupby_label': self.groupby_field_id.field_description or '',
            'series_label': self.series_field_id.field_description or '',
            'x_label': self.measure_field_id.field_description or _('Count'),
            'y_label': self.measure2_field_id.field_description or _('Count'),
            'text_content': self.text_content or '',
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
        result = {}
        for widget in self:
            try:
                result[widget.id] = widget._compute_data()
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

    def _compute_data(self):
        self.ensure_one()
        if self.data_mode == 'content':
            return {}
        if not self.model_id:
            return {'error': _('Choose a model for this widget.')}
        if self.model_name not in self.env:
            return {'error': _('Model "%s" is not available.', self.model_name)}
        Model = self.env[self.model_name]
        domain = self._get_domain()
        if self.data_mode == 'single':
            return self._compute_single(Model, domain)
        if self.data_mode == 'points':
            return self._compute_points(Model, domain)
        return self._compute_grouped(Model, domain)

    def _get_domain(self):
        if not self.domain:
            return []
        today = fields.Date.context_today(self)
        eval_context = {
            **self.env['ir.rule']._eval_context(),
            'uid': self.env.uid,
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
        self._check_field(Model, self.measure_field_id)
        spec = self._aggregate_spec(self.measure_field_id, self.aggregate)
        rows = Model._read_group(domain, [], [spec])
        value = rows[0][0] if rows else 0
        return {'value': float(value or 0)}

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

        keys = list(groups)
        if self.sort == 'value_desc':
            keys.sort(key=lambda k: groups[k]['value'], reverse=True)
        elif self.sort == 'value_asc':
            keys.sort(key=lambda k: groups[k]['value'])
        else:
            keys.sort(key=lambda k: self._sort_key(groups[k]['raw']))
        limit = min(self.limit or MAX_GROUPS, MAX_GROUPS)
        keys = keys[:limit]

        labels = [self._format_group(group_field, self.groupby_interval, groups[k]['raw']) for k in keys]
        data = {
            'labels': labels,
            'values': [groups[k]['value'] for k in keys],
            'counts': [groups[k]['count'] for k in keys],
        }
        if self.uses_second_measure:
            data['values2'] = [groups[k]['value2'] for k in keys]
        if series_field:
            series_keys = sorted(series, key=lambda s: self._sort_key(series[s]))
            data['series'] = [
                {
                    'label': self._format_group(series_field, self.series_interval, series[s]),
                    'values': [cells.get((k, s), 0.0) for k in keys],
                }
                for s in series_keys
            ]
        return data

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

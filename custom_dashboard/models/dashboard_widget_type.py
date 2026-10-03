from odoo import fields, models


class CustomDashboardWidgetType(models.Model):
    """A widget the dashboard editor offers in its palette.

    ``code`` picks the front-end renderer and ``data_mode`` how the server
    fetches data, so new rows only work for codes the renderer knows. Users
    can rename, re-order, re-categorise and archive the shipped types.
    """
    _name = 'custom.dashboard.widget.type'
    _description = 'Dashboard Widget Type'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    code = fields.Char(
        string='Renderer Code', required=True,
        help='Technical key of the front-end renderer (e.g. column, bar, kpi).',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    category_id = fields.Many2one(
        'custom.dashboard.widget.category', string='Category', ondelete='restrict',
    )
    icon = fields.Char(
        string='Icon', default='fa-bar-chart',
        help='FontAwesome icon class shown in the widget palette.',
    )
    description = fields.Char(string='Description', translate=True)
    # Technical: drives how the server fetches data for this widget.
    data_mode = fields.Selection(
        [
            ('grouped', 'Grouped values'),
            ('single', 'Single value'),
            ('points', 'Record points'),
            ('map', 'Map'),
            ('content', 'Static content'),
        ],
        string='Data Mode', required=True, default='grouped',
    )
    supports_series = fields.Boolean(
        string='Supports Series',
        help='The widget can split its data by a second group-by field.',
    )
    requires_series = fields.Boolean(string='Requires Series')
    uses_second_measure = fields.Boolean(
        string='Uses Second Measure',
        help='The widget plots a second measure (line of a combo chart, Y axis of a scatter, ...).',
    )
    default_width = fields.Integer(string='Default Width', default=4, help='Grid columns (1-12).')
    default_height = fields.Integer(string='Default Height', default=4, help='Grid rows.')

    _code_uniq = models.Constraint('UNIQUE(code)', 'Each renderer code can only be used once.')

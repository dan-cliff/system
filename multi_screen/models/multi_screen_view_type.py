from odoo import fields, models


class MultiScreenViewType(models.Model):
    """A kind of view (List, Form, ...) a workspace can be opened from."""

    _name = 'multi.screen.view.type'
    _description = 'Workspace View Type'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        help="The view's technical type in Odoo, e.g. list, kanban, form, calendar.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint('UNIQUE (code)', 'Another view type already uses this code.')

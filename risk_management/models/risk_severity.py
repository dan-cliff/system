import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

COLOR_RE = re.compile(r'^#(?:[0-9a-fA-F]{3}){1,2}$')


class RiskSeverity(models.Model):
    _name = 'risk.severity'
    _description = 'Risk Severity'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    bg_color = fields.Char(
        string='Background Colour', required=True, default='#FFFFFF',
        help='Cell background colour used for this severity in the risk matrix.',
    )
    text_color = fields.Char(
        string='Text Colour', required=True, default='#000000',
        help='Label colour used for this severity in the risk matrix - pick something that '
             'contrasts well against the background colour.',
    )
    description = fields.Text()
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'A severity with this name already exists.',
    )

    @api.constrains('bg_color', 'text_color')
    def _check_colors(self):
        for severity in self:
            for field_name in ('bg_color', 'text_color'):
                value = severity[field_name]
                if value and not COLOR_RE.match(value):
                    raise ValidationError(
                        '%s must be a hex colour code, e.g. #FF0000.' % severity._fields[field_name].string
                    )

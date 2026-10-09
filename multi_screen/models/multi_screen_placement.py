from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MultiScreenPlacement(models.Model):
    """Where on a screen a workspace window goes, as percentages of that
    screen's usable area (so the same placement works on any size screen)."""

    _name = 'multi.screen.placement'
    _description = 'Window Placement'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    left_pct = fields.Float(string='Left (%)', default=0.0, digits=(5, 1))
    top_pct = fields.Float(string='Top (%)', default=0.0, digits=(5, 1))
    width_pct = fields.Float(string='Width (%)', default=100.0, digits=(5, 1))
    height_pct = fields.Float(string='Height (%)', default=100.0, digits=(5, 1))

    @api.constrains('left_pct', 'top_pct', 'width_pct', 'height_pct')
    def _check_geometry(self):
        for placement in self:
            _check_rect(placement)


def _check_rect(record):
    """Shared by placements and windows: the rectangle must fit on the screen."""
    if min(record.left_pct, record.top_pct) < 0 or record.width_pct <= 0 or record.height_pct <= 0:
        raise ValidationError(record.env._('Left and top must be 0 or more, and width and height more than 0.'))
    if record.left_pct + record.width_pct > 100.01 or record.top_pct + record.height_pct > 100.01:
        raise ValidationError(record.env._('The window must fit on the screen: left + width and top + height '
                                           'can be at most 100%.'))

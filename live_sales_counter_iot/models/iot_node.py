from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.embroidery_jobbing.models.iot_node import ROLE_DISPLAY


class IotNode(models.Model):
    """What a Display Screen Node shows: an Embroidery status board or a
    Live Sales Counter."""
    _inherit = 'iot.node'

    # Technical choice the screen's page depends on.
    display_content = fields.Selection(
        [('embroidery_board', 'Embroidery Status Board'), ('live_counter', 'Live Sales Counter')],
        string='Shows', default='embroidery_board', required=True, tracking=True,
    )
    live_counter_id = fields.Many2one(
        'live.counter', string='Live Sales Counter', ondelete='restrict', tracking=True,
        help='The live sales page the screen shows. Change it here and the screen switches within a few seconds.',
    )

    def _shows_live_counter(self):
        self.ensure_one()
        return self.role == ROLE_DISPLAY and self.display_content == 'live_counter'

    @api.constrains('role', 'embroidery_board_id', 'display_content')
    def _check_embroidery_board(self):
        # Replaces Embroidery's check: a board is only needed when the screen shows one.
        for node in self:
            if node.role == ROLE_DISPLAY and node.display_content == 'embroidery_board' \
                    and not node.embroidery_board_id:
                raise ValidationError(_('Choose the status board %s shows.', node.name))

    @api.constrains('role', 'display_content', 'live_counter_id')
    def _check_live_counter(self):
        for node in self:
            if node._shows_live_counter() and not node.live_counter_id:
                raise ValidationError(_('Choose the live sales counter %s shows.', node.name))

    def write(self, vals):
        switched = self.browse()
        if 'display_content' in vals or 'live_counter_id' in vals:
            switched = self.filtered(lambda n: n.role == ROLE_DISPLAY)
        result = super().write(vals)
        # Make the open page reload into what the screen shows now.
        for node in switched:
            node.reload_counter += 1
        return result

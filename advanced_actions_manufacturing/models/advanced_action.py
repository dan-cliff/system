from odoo import api, fields, models


class AdvancedAction(models.Model):
    _inherit = 'advanced.action'

    source_app = fields.Selection(
        selection_add=[('manufacturing', 'Manufacturing')], ondelete={'manufacturing': 'set default'},
    )
    production_id = fields.Many2one(
        'mrp.production', string='Manufacturing Order', ondelete='cascade', index='btree_not_null',
    )

    @api.model
    def _action_sources(self):
        return super()._action_sources() + [('production_id', 'manufacturing')]

from odoo import api, fields, models


class AdvancedAction(models.Model):
    _inherit = 'advanced.action'

    source_app = fields.Selection(
        selection_add=[('zoo', 'Zoo Manager')], ondelete={'zoo': 'set default'},
    )
    zoo_animal_id = fields.Many2one(
        'zoo.animal', string='Animal', ondelete='cascade', index='btree_not_null',
    )
    zoo_enclosure_id = fields.Many2one(
        'zoo.enclosure', string='Enclosure', ondelete='cascade', index='btree_not_null',
    )

    @api.model
    def _action_sources(self):
        return super()._action_sources() + [('zoo_animal_id', 'zoo'), ('zoo_enclosure_id', 'zoo')]

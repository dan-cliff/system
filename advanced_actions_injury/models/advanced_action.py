from odoo import api, fields, models


class AdvancedAction(models.Model):
    _inherit = 'advanced.action'

    source_app = fields.Selection(
        selection_add=[('injury', 'Injury Management')], ondelete={'injury': 'set default'},
    )
    injury_case_id = fields.Many2one(
        'injury.rtw.case', string='RTW Case', ondelete='cascade', index='btree_not_null',
    )

    @api.model
    def _action_sources(self):
        return super()._action_sources() + [('injury_case_id', 'injury')]

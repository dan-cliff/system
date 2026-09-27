from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    zoo_feeding_id = fields.Many2one('zoo.feeding', string='Feeding Round', index='btree_not_null', readonly=True)

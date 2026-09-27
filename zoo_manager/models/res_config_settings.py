from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    zoo_feed_warehouse_ids = fields.Many2many(
        related='company_id.zoo_feed_warehouse_ids', readonly=False,
        string='Warehouses',
        help='Which Warehouse/s are feed items stored in?',
    )
    zoo_feed_categ_ids = fields.Many2many(
        related='company_id.zoo_feed_categ_ids', readonly=False,
        string='Product Categories',
        help='Which Product Categories contain Feed items?',
    )

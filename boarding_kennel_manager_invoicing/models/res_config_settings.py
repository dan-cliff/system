from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kennel_warehouse_ids = fields.Many2many(related='company_id.kennel_warehouse_ids', readonly=False)
    kennel_product_categ_ids = fields.Many2many(related='company_id.kennel_product_categ_ids', readonly=False)

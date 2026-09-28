from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kennel_observation_times = fields.Char(related='company_id.kennel_observation_times', readonly=False)
    kennel_invoicing = fields.Boolean(related='company_id.kennel_invoicing', readonly=False)
    kennel_warehouse_ids = fields.Many2many(related='company_id.kennel_warehouse_ids', readonly=False)
    kennel_product_categ_ids = fields.Many2many(related='company_id.kennel_product_categ_ids', readonly=False)

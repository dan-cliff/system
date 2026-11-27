from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    purchase_account_type_ids = fields.Many2many(
        related='company_id.purchase_account_type_ids', readonly=False)

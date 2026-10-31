from odoo import fields, models


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'advanced.accounts.mixin']

    # Settings > Purchasing > Account Types to Purchase From: when set, the
    # Supplier (Account) and Contact pickers only offer Accounts of those types.
    adv_purchase_account_type_ids = fields.Many2many(related='company_id.purchase_account_type_ids')

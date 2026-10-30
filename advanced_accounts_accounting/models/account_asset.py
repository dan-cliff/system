from odoo import models


class AccountAssetAsset(models.Model):
    _name = 'account.asset.asset'
    _inherit = ['account.asset.asset', 'advanced.accounts.mixin']

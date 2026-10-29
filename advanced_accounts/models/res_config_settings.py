from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Each support app moves one app's customer fields to Accounts and Contacts.
    module_advanced_accounts_crm = fields.Boolean('CRM')
    module_advanced_accounts_sale = fields.Boolean('Sales')
    module_advanced_accounts_account = fields.Boolean('Invoicing')
    module_advanced_accounts_project = fields.Boolean('Project')
    module_advanced_accounts_helpdesk = fields.Boolean('Helpdesk')
    module_advanced_accounts_feature_suggestions = fields.Boolean('Feature Suggestions')
    module_advanced_accounts_print_farm = fields.Boolean('Print Farm Jobs')
    module_advanced_accounts_embroidery = fields.Boolean('Embroidery Jobs')
    module_advanced_accounts_checklists = fields.Boolean('Checklists')
    module_advanced_accounts_signr = fields.Boolean("Sign'r")
    module_advanced_accounts_purchase = fields.Boolean('Purchase')
    module_advanced_accounts_expense = fields.Boolean('Expenses')
    module_advanced_accounts_pos = fields.Boolean('Point of Sale')
    module_advanced_accounts_asset = fields.Boolean('Asset Management')

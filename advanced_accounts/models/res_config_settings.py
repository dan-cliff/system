from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Each support app moves one app's customer fields to Accounts and Contacts.
    module_advanced_accounts_crm = fields.Boolean("Accounts and Contacts in CRM")
    module_advanced_accounts_sale = fields.Boolean("Accounts and Contacts in Sales")
    module_advanced_accounts_account = fields.Boolean("Accounts and Contacts in Invoicing")
    module_advanced_accounts_project = fields.Boolean("Accounts and Contacts in Project")
    module_advanced_accounts_helpdesk = fields.Boolean("Accounts and Contacts in Helpdesk")
    module_advanced_accounts_feature_suggestions = fields.Boolean("Accounts and Contacts in Feature Suggestions")
    module_advanced_accounts_print_farm = fields.Boolean("Accounts and Contacts in Print Farm Jobs")
    module_advanced_accounts_embroidery = fields.Boolean("Accounts and Contacts in Embroidery Jobs")
    module_advanced_accounts_checklists = fields.Boolean("Accounts and Contacts in Checklists")
    module_advanced_accounts_signr = fields.Boolean("Accounts and Contacts in Sign'r")
    module_advanced_accounts_purchase = fields.Boolean("Accounts and Contacts in Purchase")
    module_advanced_accounts_expense = fields.Boolean("Accounts and Contacts in Expenses")
    module_advanced_accounts_pos = fields.Boolean("Accounts and Contacts in Point of Sale")
    module_advanced_accounts_asset = fields.Boolean("Accounts and Contacts in Asset Management")

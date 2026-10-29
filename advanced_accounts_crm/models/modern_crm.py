from odoo import models


class ModernCrmOpportunity(models.Model):
    _name = 'modern.crm.opportunity'
    _inherit = ['modern.crm.opportunity', 'advanced.accounts.mixin']
    # The opportunity keeps the Account in partner_id and the Primary Contact
    # in contact_id.
    _adv_account_partner_field = 'partner_id'
    _adv_partner_field = 'contact_id'


class ModernCrmContactRole(models.Model):
    _name = 'modern.crm.contact.role'
    _inherit = ['modern.crm.contact.role', 'advanced.accounts.mixin']


class ModernCrmContract(models.Model):
    _name = 'modern.crm.contract'
    _inherit = ['modern.crm.contract', 'advanced.accounts.mixin']
    _adv_account_partner_field = 'partner_id'
    _adv_partner_field = False


class ModernCrmLead(models.Model):
    _name = 'modern.crm.lead'
    _inherit = ['modern.crm.lead', 'advanced.accounts.mixin']

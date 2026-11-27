"""Configurable choice lists, managed under CRM > Configuration."""
from random import randint

from odoo import fields, models


class ModernCrmOptionMixin(models.AbstractModel):
    _name = 'modern.crm.option.mixin'
    _description = 'CRM Option'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()


class ModernCrmLeadSource(models.Model):
    _name = 'modern.crm.lead.source'
    _inherit = 'modern.crm.option.mixin'
    _description = 'CRM Lead Source'

    _name_uniq = models.Constraint('unique (name)', 'A lead source with this name already exists.')


class ModernCrmIndustry(models.Model):
    _name = 'modern.crm.industry'
    _inherit = 'modern.crm.option.mixin'
    _description = 'CRM Industry'

    _name_uniq = models.Constraint('unique (name)', 'An industry with this name already exists.')


class ModernCrmLeadRating(models.Model):
    _name = 'modern.crm.lead.rating'
    _inherit = 'modern.crm.option.mixin'
    _description = 'CRM Lead Rating'

    def _default_color(self):
        return randint(1, 11)

    color = fields.Integer(default=_default_color)

    _name_uniq = models.Constraint('unique (name)', 'A lead rating with this name already exists.')


class ModernCrmDisqualifyReason(models.Model):
    _name = 'modern.crm.disqualify.reason'
    _inherit = 'modern.crm.option.mixin'
    _description = 'CRM Lead Disqualify Reason'

    _name_uniq = models.Constraint('unique (name)', 'A disqualify reason with this name already exists.')


class ModernCrmOpportunityType(models.Model):
    _name = 'modern.crm.opportunity.type'
    _inherit = 'modern.crm.option.mixin'
    _description = 'CRM Opportunity Type'

    _name_uniq = models.Constraint('unique (name)', 'An opportunity type with this name already exists.')


class ModernCrmForecastCategory(models.Model):
    _name = 'modern.crm.forecast.category'
    _inherit = 'modern.crm.option.mixin'
    _description = 'CRM Forecast Category'

    _name_uniq = models.Constraint('unique (name)', 'A forecast category with this name already exists.')


class ModernCrmLostReason(models.Model):
    _name = 'modern.crm.lost.reason'
    _inherit = 'modern.crm.option.mixin'
    _description = 'CRM Opportunity Lost Reason'

    _name_uniq = models.Constraint('unique (name)', 'A lost reason with this name already exists.')


class ModernCrmContactRoleType(models.Model):
    _name = 'modern.crm.contact.role.type'
    _inherit = 'modern.crm.option.mixin'
    _description = 'CRM Contact Role'

    _name_uniq = models.Constraint('unique (name)', 'A contact role with this name already exists.')

"""Configurable choice lists, managed under Zoo Manager > Configuration."""
from odoo import fields, models


class ZooOptionMixin(models.AbstractModel):
    _name = 'zoo.option.mixin'
    _description = 'Zoo Configurable Option'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class ZooEnclosureType(models.Model):
    _name = 'zoo.enclosure.type'
    _description = 'Enclosure Type'
    _inherit = ['zoo.option.mixin']


class ZooAnimalOrigin(models.Model):
    _name = 'zoo.animal.origin'
    _description = 'Animal Origin'
    _inherit = ['zoo.option.mixin']


class ZooConservationStatus(models.Model):
    _name = 'zoo.conservation.status'
    _description = 'Conservation Status'
    _inherit = ['zoo.option.mixin']

    code = fields.Char(help='Short code, e.g. the IUCN Red List category (LC, VU, EN).')

    def _compute_display_name(self):
        for status in self:
            status.display_name = f'{status.name} ({status.code})' if status.code else status.name


class ZooHealthRecordType(models.Model):
    _name = 'zoo.health.record.type'
    _description = 'Health Record Type'
    _inherit = ['zoo.option.mixin']


class ZooDietFrequency(models.Model):
    _name = 'zoo.diet.frequency'
    _description = 'Diet Frequency'
    _inherit = ['zoo.option.mixin']


class ZooFeedingConsumption(models.Model):
    _name = 'zoo.feeding.consumption'
    _description = 'Food Consumption'
    _inherit = ['zoo.option.mixin']

    refused = fields.Boolean(help='The food was refused. Such feeding rounds are highlighted and can be filtered.')

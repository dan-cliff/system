"""Configurable choice lists, managed under Boarding Kennel Manager > Configuration."""
from odoo import fields, models


class KennelOptionMixin(models.AbstractModel):
    _name = 'kennel.option.mixin'
    _description = 'Boarding Kennel Configurable Option'
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', index=True,
        help='Leave empty to share this option with every company.',
    )


class KennelSpecies(models.Model):
    _name = 'kennel.species'
    _description = 'Species'
    _inherit = ['kennel.option.mixin']


class KennelSex(models.Model):
    _name = 'kennel.sex'
    _description = 'Sex'
    _inherit = ['kennel.option.mixin']


class KennelYardType(models.Model):
    _name = 'kennel.yard.type'
    _description = 'Yard Type'
    _inherit = ['kennel.option.mixin']


class KennelYardFeature(models.Model):
    _name = 'kennel.yard.feature'
    _description = 'Yard Feature'
    _inherit = ['kennel.option.mixin']


class KennelFrequency(models.Model):
    _name = 'kennel.frequency'
    _description = 'Frequency'
    _inherit = ['kennel.option.mixin']


class KennelMedicationRoute(models.Model):
    _name = 'kennel.medication.route'
    _description = 'Medication Route'
    _inherit = ['kennel.option.mixin']


class KennelDoseOutcome(models.Model):
    _name = 'kennel.dose.outcome'
    _description = 'Dose Outcome'
    _inherit = ['kennel.option.mixin']

    problem = fields.Boolean(
        string='Needs Attention',
        help='The dose was not (fully) taken. Such entries are highlighted and can be filtered.',
    )


class KennelObservationType(models.Model):
    _name = 'kennel.observation.type'
    _description = 'Observation Type'
    _inherit = ['kennel.option.mixin']

    concern = fields.Boolean(
        help='Observations of this type are flagged as a concern by default.',
    )

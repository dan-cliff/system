"""Configurable choice lists, managed under Boarding Kennel Manager > Configuration."""
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

TIME_RE = re.compile(r'^([01]?\d|2[0-3]):([0-5]\d)$')


def parse_times(text):
    """'08:00, 17:30' -> [(8, 0), (17, 30)], sorted and without duplicates. Raises ValueError on a bad time."""
    times = set()
    for part in (text or '').replace(';', ',').split(','):
        part = part.strip()
        if not part:
            continue
        match = TIME_RE.match(part)
        if not match:
            raise ValueError(part)
        times.add((int(match.group(1)), int(match.group(2))))
    return sorted(times)


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

    times = fields.Char(
        string='Times of Day',
        help='24-hour times separated by commas, e.g. "08:00, 17:00". Each one puts a feed or dose on the '
             'daily to-do list. Leave empty for "as needed" (no scheduled tasks).',
    )

    @api.constrains('times')
    def _check_times(self):
        for frequency in self:
            try:
                parse_times(frequency.times)
            except ValueError as bad:
                raise ValidationError(self.env._(
                    '%(frequency)s: "%(time)s" is not a time. Use 24-hour times like 08:00, 17:30.',
                    frequency=frequency.name, time=bad))

    def _get_times(self):
        """[(hour, minute), ...] for this frequency; empty when there's no frequency or no times."""
        return parse_times(self.times) if self else []


class KennelFeedConsumption(models.Model):
    _name = 'kennel.feed.consumption'
    _description = 'Food Eaten'
    _inherit = ['kennel.option.mixin']

    problem = fields.Boolean(
        string='Needs Attention',
        help='The animal didn\'t eat (all of) its food. Such feeds are highlighted and can be filtered.',
    )


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

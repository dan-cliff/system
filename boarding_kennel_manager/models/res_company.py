import pytz

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .kennel_options import parse_times


class ResCompany(models.Model):
    _inherit = 'res.company'

    kennel_observation_times = fields.Char(
        string='Observation Rounds', default='09:00, 16:00',
        help='24-hour times separated by commas. Each one puts an observation for every checked-in '
             'animal on the daily to-do list.',
    )

    @api.constrains('kennel_observation_times')
    def _check_kennel_observation_times(self):
        for company in self:
            try:
                parse_times(company.kennel_observation_times)
            except ValueError as bad:
                raise ValidationError(self.env._(
                    '"%s" is not a time. Use 24-hour times like 09:00, 16:00.', bad))

    def _kennel_tz(self):
        """Timezone the kennel's daily task times are in: the company's, else the current user's."""
        self.ensure_one()
        return pytz.timezone(self.partner_id.tz or self.env.user.tz or 'UTC')

    def _kennel_observation_times(self):
        self.ensure_one()
        return parse_times(self.kennel_observation_times)

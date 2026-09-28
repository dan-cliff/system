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

    kennel_invoicing = fields.Boolean(
        string='Integrate Bookings with Invoicing',
        help='When enabled, bookings will have the ability to raise an invoice in the Accounting app and '
             'reflect the payment status in the booking.',
    )

    # Control Plane: the interactive enclosure screens. Both choices drive how the screens are drawn,
    # so they are fixed selections rather than configurable option lists.
    kennel_cp_theme = fields.Selection(
        [('system', 'System'), ('light', 'Light'), ('dark', 'Dark')],
        string='Control Plane Theme', default='system', required=True,
        help='Light or dark mode for the Control Plane, or System to follow the setting of the device it is on.',
    )
    kennel_cp_background = fields.Selection(
        [('image', 'Image'), ('colour', 'Custom Colour'), ('branding', 'Company Branding')],
        string='Background', default='branding', required=True,
    )
    kennel_cp_background_image = fields.Image(string='Control Plane Background Image', max_width=3840, max_height=2160)
    kennel_cp_image_transparency = fields.Integer(
        string='Image Transparency', default=0,
        help='0% shows the image as it is, 100% makes it fully transparent.',
    )
    kennel_cp_colour_light = fields.Char(string='Light Mode Colour', default='#F5F5F5')
    kennel_cp_colour_dark = fields.Char(string='Dark Mode Colour', default='#1E1E1E')
    kennel_cp_refresh_minutes = fields.Integer(
        string='Auto Refresh Interval', default=5,
        help='How many minutes should the Control Plane be idle before it\'s automatically refreshed? '
             'To disable auto refresh, set the interval to 0.',
    )

    @api.constrains('kennel_cp_refresh_minutes')
    def _check_kennel_cp_refresh_minutes(self):
        for company in self:
            if company.kennel_cp_refresh_minutes < 0:
                raise ValidationError(self.env._('The auto refresh interval can\'t be negative. Use 0 to turn it off.'))

    @api.constrains('kennel_cp_image_transparency')
    def _check_kennel_cp_image_transparency(self):
        for company in self:
            if not 0 <= company.kennel_cp_image_transparency <= 100:
                raise ValidationError(self.env._('The image transparency must be between 0% and 100%.'))

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

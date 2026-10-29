from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    onsite_systray = fields.Boolean(
        string='Sign In from Odoo', default=True,
        help='Show the Sign In / Out button in the top toolbar for employees allowed to use it.',
    )
    onsite_location_tracking = fields.Boolean(
        string='Record Location',
        help='When signing in or out from Odoo, record the GPS position (if the device allows it), '
             'IP address and browser.',
    )
    onsite_auto_sign_out = fields.Boolean(
        string='Automatic Sign Out',
        help='Sign out employees who forget to, when they did not sign in at a kiosk. '
             'Kiosk sign ins follow the kiosk\'s own setting.',
    )
    onsite_auto_sign_out_hours = fields.Float(string='Sign Out After (Hours)', default=12.0)

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

    # ── Extra hours ────────────────────────────────────────────────────────
    onsite_overtime_validation = fields.Selection(
        [('no_validation', 'Approved Automatically'), ('by_manager', 'Approved by a Manager')],
        string='Extra Hours Approval', default='no_validation',
        help='Approved by a Manager: extra hours wait for someone with the "Attendances: Approve '
             'Extra Hours" permission.',
    )
    onsite_absence_management = fields.Boolean(
        string='Absence Management',
        help='Count missing hours as negative extra hours, including working days with no '
             'attendance at all. Does not apply to flexible working schedules.',
    )
    onsite_display_overtime = fields.Boolean(
        string='Display Extra Hours', help='Show extra hours on employees and in the toolbar.',
    )

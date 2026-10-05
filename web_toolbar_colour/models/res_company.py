from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    toolbar_color = fields.Char(
        string='Toolbar Colour',
        help='Hex colour (e.g. #1f6f43) for the top toolbar while this company is active. '
             'Leave blank to use the Odoo default.',
    )

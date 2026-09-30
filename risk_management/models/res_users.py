from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    team_leader_id = fields.Many2one(
        'res.users', string='Team Leader', domain="[('share', '=', False)]",
        help='Used to default the Risk Approver on a Risk Assessment when this user is the Risk Assessment Owner.',
    )

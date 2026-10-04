from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    help_centre_helpdesk_enabled = fields.Boolean(
        'Enable Helpdesk Ticket Creation from Help Widget',
        config_parameter='help_centre.helpdesk_enabled',
    )
    help_centre_helpdesk_team_id = fields.Many2one(
        'helpdesk.team',
        string='Helpdesk Team',
        help='Which Team should receive helpdesk tickets from the Help widget?',
    )

    @api.model
    def _help_centre_helpdesk_enabled(self):
        params = self.env['ir.config_parameter'].sudo()
        return params.get_param('help_centre.helpdesk_enabled', 'False') == 'True'

    def get_values(self):
        res = super().get_values()
        team_id = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'help_centre.helpdesk_team_id', '0'
            ) or '0'
        )
        team = self.env['helpdesk.team'].browse(team_id).exists()
        if team:
            res['help_centre_helpdesk_team_id'] = team.id
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'help_centre.helpdesk_team_id',
            str(self.help_centre_helpdesk_team_id.id)
            if self.help_centre_helpdesk_team_id else '0',
        )

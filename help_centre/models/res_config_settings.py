from odoo import _, api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Help Centre branding ───────────────────────────────────────────────────

    help_centre_name = fields.Char(
        'Help Centre Name',
        config_parameter='help_centre.name',
        default='Help Centre',
    )
    help_centre_tagline = fields.Char(
        'Tagline',
        config_parameter='help_centre.tagline',
        default='Find answers, guides, and step-by-step instructions',
    )
    help_centre_primary_color = fields.Char(
        'Primary Colour',
        config_parameter='help_centre.primary_color',
        default='#5b4fc8',
        help='Hex colour code used for buttons, highlights, and the widget toggle '
             'across both the website and the backend KC Bot. Example: #5b4fc8',
    )
    help_centre_ai_name = fields.Char(
        'AI Assistant Name',
        config_parameter='help_centre.ai_name',
        default='KC Bot',
        help='Friendly name displayed in the chatbot panel header and search results.',
    )
    help_centre_ai_welcome_message = fields.Char(
        'Welcome Message',
        config_parameter='help_centre.ai_welcome_message',
        help='Opening message shown when a user first opens the Ask AI tab. '
             'Leave blank to use the default greeting.',
    )

    # ── Widget visibility & position ───────────────────────────────────────────

    help_centre_widget_all_pages = fields.Boolean(
        'Show KC Bot widget on all website pages',
        config_parameter='help_centre.widget_all_pages',
        help='When enabled the floating Help widget appears on every page of '
             'the website, not just /help pages.',
    )

    help_centre_widget_position = fields.Selection([
        ('bottom_right', 'Bottom Right'),
        ('bottom_left', 'Bottom Left'),
        ('top_right', 'Top Right'),
        ('top_left', 'Top Left'),
    ], string='Widget Position',
        config_parameter='help_centre.widget_position',
        default='bottom_right',
        help='Corner of the page where the floating KC Bot button is anchored.',
    )

    # ── AI model override (optional) ───────────────────────────────────────────

    help_centre_ai_model = fields.Char(
        'AI Model Override',
        config_parameter='help_centre.ai_model',
        help='Leave blank to use the default model for each provider. '
             'Set to e.g. "claude-opus-4-5" to override when using Anthropic.',
    )

    # ── Helpdesk integration ───────────────────────────────────────────────────

    help_centre_helpdesk_installed = fields.Boolean(
        compute='_compute_helpdesk_installed',
        string='Helpdesk Installed',
    )
    help_centre_helpdesk_enabled = fields.Boolean(
        'Enable Helpdesk Ticket Creation from Help Widget',
        config_parameter='help_centre.helpdesk_enabled',
    )
    help_centre_helpdesk_team_id = fields.Many2one(
        'helpdesk.team',
        string='Helpdesk Team',
        help='Which Team should receive helpdesk tickets from the Help widget?',
    )

    def _compute_helpdesk_installed(self):
        installed = bool(self.env['ir.module.module'].sudo().search_count([
            ('name', '=', 'helpdesk'), ('state', '=', 'installed'),
        ]))
        for rec in self:
            rec.help_centre_helpdesk_installed = installed

    def get_values(self):
        res = super().get_values()
        team_id = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'help_centre.helpdesk_team_id', '0'
            ) or '0'
        )
        if team_id:
            res['help_centre_helpdesk_team_id'] = team_id
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'help_centre.helpdesk_team_id',
            str(self.help_centre_helpdesk_team_id.id)
            if self.help_centre_helpdesk_team_id else '0',
        )

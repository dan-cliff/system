from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    twilio_email_enabled = fields.Boolean(
        string='Enable Twilio Emails',
        config_parameter='twilio_notifications.enabled',
        help='Setup your notifications to route via your Twilio email domain using the API',
    )
    twilio_sid = fields.Char(
        string='Twilio SID',
        config_parameter='twilio_notifications.sid',
        help='Used to authenticate with the Twilio Email API.',
    )
    twilio_secret = fields.Char(
        string='Twilio Secret',
        config_parameter='twilio_notifications.secret',
        help='Used to authenticate with the Twilio Email API.',
    )
    twilio_from_email = fields.Char(
        string='From Email',
        config_parameter='twilio_notifications.from_email',
        help='Email address notifications are sent from via the Twilio Email API.',
    )
    twilio_from_name = fields.Char(
        string='From Name',
        config_parameter='twilio_notifications.from_name',
        help='Name notifications are sent from via the Twilio Email API.',
    )

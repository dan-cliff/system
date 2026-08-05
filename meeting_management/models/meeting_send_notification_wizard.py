import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MeetingSendNotificationWizard(models.TransientModel):
    _name = 'meeting.send.notification.wizard'
    _description = 'Send Meeting Notification'

    meeting_id = fields.Many2one(
        'meeting.meeting',
        string='Meeting',
        required=True,
        readonly=True,
    )
    notification_template_id = fields.Many2one(
        'meeting.notification.template',
        string='Notification Template',
        required=True,
    )
    preview_subject = fields.Char(
        string='Subject Preview',
        compute='_compute_preview',
    )
    preview_body = fields.Html(
        string='Body Preview',
        compute='_compute_preview',
    )
    recipient_names = fields.Char(
        string='Recipients',
        compute='_compute_preview',
    )

    @api.depends('notification_template_id', 'meeting_id')
    def _compute_preview(self):
        for wizard in self:
            if wizard.notification_template_id and wizard.meeting_id:
                tmpl = wizard.notification_template_id
                meeting = wizard.meeting_id
                wizard.preview_subject = tmpl._render_placeholder(tmpl.subject or '', meeting)
                wizard.preview_body = tmpl._render_placeholder(tmpl.body_html or '', meeting)
                recipients = tmpl._get_recipients_for_meeting(meeting)
                wizard.recipient_names = ', '.join(recipients.mapped('name'))
            else:
                wizard.preview_subject = ''
                wizard.preview_body = ''
                wizard.recipient_names = ''

    def action_send(self):
        self.ensure_one()
        if not self.notification_template_id:
            raise UserError(_('Please select a notification template.'))
        self.notification_template_id.action_send_for_meeting(self.meeting_id)
        return {'type': 'ir.actions.act_window_close'}

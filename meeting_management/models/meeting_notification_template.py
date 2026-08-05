import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PLACEHOLDER_HELP = """
Available placeholders:
  {meeting_name}        - Meeting title
  {meeting_reference}   - Meeting reference number
  {meeting_date}        - Meeting start date/time
  {meeting_end}         - Meeting end date/time
  {meeting_location}    - Meeting location
  {meeting_type}        - Meeting type (In Person / Virtual / Hybrid)
  {chairperson}         - Chairperson name
  {secretary}           - Secretary name
  {invitees}            - Comma-separated list of invitee names
  {teams_join_url}      - Microsoft Teams join URL
  {agenda_count}        - Number of agenda items
  {action_items_count}  - Number of action items
  {company_name}        - Company name
"""


class MeetingNotificationTemplate(models.Model):
    _name = 'meeting.notification.template'
    _description = 'Meeting Notification Template'
    _order = 'sequence, name'

    name = fields.Char(string='Template Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(string='Internal Description')

    # Trigger configuration
    trigger = fields.Selection([
        ('manual', 'Manual (Send on Demand)'),
        ('on_invite', 'When Meeting is Scheduled'),
        ('before_meeting', 'Before Meeting'),
        ('on_start', 'When Meeting Starts'),
        ('after_meeting', 'After Meeting Completion'),
        ('minutes_ready', 'When Minutes are Ready'),
    ], string='Trigger', required=True, default='manual')
    trigger_hours = fields.Integer(
        string='Hours Before/After',
        default=24,
        help='Number of hours before or after the meeting. Used for Before/After triggers.',
    )

    # Email content
    notification_type = fields.Selection([
        ('email', 'Email Notification'),
        ('internal', 'Internal Note (Chatter)'),
    ], string='Notification Type', required=True, default='email')
    subject = fields.Char(
        string='Email Subject',
        help=PLACEHOLDER_HELP,
    )
    body_html = fields.Html(
        string='Email Body',
        help=PLACEHOLDER_HELP,
        sanitize=False,
    )

    # Recipients
    recipient_type = fields.Selection([
        ('all_invitees', 'All Invitees'),
        ('chairperson', 'Chairperson Only'),
        ('secretary', 'Secretary Only'),
        ('chair_and_secretary', 'Chairperson & Secretary'),
        ('custom', 'Custom Recipients'),
    ], string='Recipients', required=True, default='all_invitees')
    recipient_ids = fields.Many2many(
        'res.partner',
        'meeting_notif_template_partner_rel',
        'template_id',
        'partner_id',
        string='Additional Recipients',
    )

    # PDF attachments
    attach_agenda = fields.Boolean(
        string='Attach Meeting Agenda PDF',
        help='Automatically attach the Meeting Agenda PDF to this notification.',
    )
    attach_minutes = fields.Boolean(
        string='Attach Meeting Minutes PDF',
        help='Automatically attach the Meeting Minutes PDF to this notification.',
    )

    # Placeholder hint
    placeholder_help = fields.Text(
        string='Available Placeholders',
        compute='_compute_placeholder_help',
    )

    @api.depends()
    def _compute_placeholder_help(self):
        for rec in self:
            rec.placeholder_help = PLACEHOLDER_HELP

    def _get_recipients_for_meeting(self, meeting):
        """Return res.partner recordset for this template's recipients given a meeting."""
        self.ensure_one()
        partners = self.env['res.partner']
        if self.recipient_type == 'all_invitees':
            partners = meeting.invitee_ids
        elif self.recipient_type == 'chairperson':
            if meeting.chairperson_id:
                partners = meeting.chairperson_id
        elif self.recipient_type == 'secretary':
            if meeting.secretary_id:
                partners = meeting.secretary_id
        elif self.recipient_type == 'chair_and_secretary':
            if meeting.chairperson_id:
                partners |= meeting.chairperson_id
            if meeting.secretary_id:
                partners |= meeting.secretary_id
        elif self.recipient_type == 'custom':
            partners = self.recipient_ids
        if self.recipient_ids and self.recipient_type != 'custom':
            partners |= self.recipient_ids
        return partners

    def _render_placeholder(self, text, meeting):
        """Replace {placeholder} tokens with actual meeting values."""
        if not text:
            return text or ''
        values = {
            'meeting_name': meeting.name or '',
            'meeting_reference': meeting.reference or '',
            'meeting_date': meeting.date_start.strftime('%d %B %Y %H:%M') if meeting.date_start else '',
            'meeting_end': meeting.date_end.strftime('%d %B %Y %H:%M') if meeting.date_end else '',
            'meeting_location': meeting.location or '',
            'meeting_type': dict(meeting._fields['meeting_type'].selection).get(meeting.meeting_type, '') if meeting.meeting_type else '',
            'chairperson': meeting.chairperson_id.name if meeting.chairperson_id else '',
            'secretary': meeting.secretary_id.name if meeting.secretary_id else '',
            'invitees': ', '.join(meeting.invitee_ids.mapped('name')),
            'teams_join_url': meeting.teams_join_url or '',
            'agenda_count': str(len(meeting.agenda_item_ids)),
            'action_items_count': str(len(meeting.action_item_ids)),
            'company_name': meeting.env.company.name or '',
        }
        try:
            return text.format(**values)
        except (KeyError, ValueError):
            return text

    def action_send_for_meeting(self, meeting):
        """Send this notification for the given meeting record."""
        self.ensure_one()
        recipients = self._get_recipients_for_meeting(meeting)
        if not recipients:
            _logger.warning('No recipients for notification template %s on meeting %s', self.name, meeting.name)
            return

        subject = self._render_placeholder(self.subject or meeting.name, meeting)
        body = self._render_placeholder(self.body_html or '', meeting)

        attachments = []

        if self.attach_agenda and meeting.state not in ('draft',):
            agenda_pdf = self._generate_agenda_pdf(meeting)
            if agenda_pdf:
                attachments.append(agenda_pdf)

        if self.attach_minutes and meeting.state == 'completed':
            minutes_pdf = self._generate_minutes_pdf(meeting)
            if minutes_pdf:
                attachments.append(minutes_pdf)

        if self.notification_type == 'email':
            mail_values = {
                'subject': subject,
                'body_html': body,
                'email_to': ','.join(r.email for r in recipients if r.email),
                'author_id': self.env.user.partner_id.id,
                'attachment_ids': [(6, 0, [a.id for a in attachments])],
            }
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()
            # Log on meeting chatter
            meeting.message_post(
                body=_('Notification sent: <b>%s</b> to %s') % (
                    self.name,
                    ', '.join(recipients.mapped('name'))
                ),
                subtype_xmlid='mail.mt_note',
            )
        else:
            # Internal note on chatter
            meeting.message_post(
                body=body,
                subject=subject,
                subtype_xmlid='mail.mt_note',
                partner_ids=recipients.ids,
            )

        return True

    def _generate_agenda_pdf(self, meeting):
        """Generate agenda PDF and return an ir.attachment record."""
        try:
            pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
                'meeting_management.report_meeting_agenda',
                meeting.ids,
            )
            filename = f'Agenda_{meeting.reference or meeting.name}.pdf'
            attachment = self.env['ir.attachment'].create({
                'name': filename,
                'type': 'binary',
                'datas': pdf_content,
                'res_model': 'meeting.meeting',
                'res_id': meeting.id,
                'mimetype': 'application/pdf',
            })
            return attachment
        except Exception as e:
            _logger.error('Failed to generate agenda PDF: %s', e)
            return None

    def _generate_minutes_pdf(self, meeting):
        """Generate minutes PDF and return an ir.attachment record."""
        try:
            pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
                'meeting_management.report_meeting_minutes',
                meeting.ids,
            )
            filename = f'Minutes_{meeting.reference or meeting.name}.pdf'
            attachment = self.env['ir.attachment'].create({
                'name': filename,
                'type': 'binary',
                'datas': pdf_content,
                'res_model': 'meeting.meeting',
                'res_id': meeting.id,
                'mimetype': 'application/pdf',
            })
            return attachment
        except Exception as e:
            _logger.error('Failed to generate minutes PDF: %s', e)
            return None

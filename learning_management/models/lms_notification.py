from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class LmsNotificationTemplate(models.Model):
    """
    Custom notification templates for the LMS.
    Administrators can design notifications triggered by events across
    any LMS model and send them to employees, managers, or custom recipients.
    """
    _name = 'lms.notification.template'
    _description = 'LMS Notification Template'
    _order = 'name'

    name = fields.Char(string='Template Name', required=True)
    active = fields.Boolean(default=True)
    description = fields.Text(string='Description')

    # Trigger configuration
    trigger_model = fields.Selection([
        ('lms.employee.record', 'Employee Training Record'),
        ('lms.session.enrollment', 'Session Enrolment'),
        ('lms.course.session', 'Course Session'),
        ('lms.course.group.assignment', 'Training Package Assignment'),
    ], string='Triggered On Model', required=True)

    trigger_event = fields.Selection([
        ('record_completed', 'Training Record Completed'),
        ('record_expired', 'Training Record Expired'),
        ('record_failed', 'Training Record Failed'),
        ('enrollment_confirmed', 'Enrolment Confirmed'),
        ('enrollment_pending', 'Enrolment Pending Approval'),
        ('session_reminder', 'Session Reminder (N days before)'),
        ('session_completed', 'Session Completed'),
        ('assignment_created', 'Training Package Assigned'),
        ('assignment_completed', 'Training Package Completed'),
        ('upload_required', 'Upload Required'),
        ('manual', 'Manual / Ad-hoc'),
    ], string='Trigger Event', required=True)

    reminder_days = fields.Integer(
        string='Reminder Days Before',
        default=3,
        help='Used when trigger event is "Session Reminder". '
             'Notification will be sent N days before the session.',
    )

    # Recipients
    recipient_type = fields.Selection([
        ('employee', 'The Employee'),
        ('manager', 'The Employee\'s Manager'),
        ('both', 'Employee and Manager'),
        ('group', 'Security Group'),
        ('custom', 'Custom Email'),
    ], string='Recipient', required=True, default='employee')
    recipient_group_id = fields.Many2one(
        'res.groups', string='Recipient Group',
        help='Notify all users in this group.',
    )
    recipient_email = fields.Char(
        string='Custom Email Address(es)',
        help='Comma-separated list of email addresses for custom recipients.',
    )

    # Message content
    subject = fields.Char(string='Subject', required=True, translate=True)
    body_html = fields.Html(
        string='Message Body',
        required=True,
        sanitize=False,
        help='''
        You can use the following placeholders:
        {{employee_name}} — Employee full name
        {{course_name}} — Course name
        {{session_name}} — Session name
        {{session_date}} — Session start date
        {{session_location}} — Session location
        {{completion_date}} — Completion date
        {{expiry_date}} — Expiry date
        {{package_name}} — Training package name
        {{manager_name}} — Manager name
        ''',
    )

    # Notification channel
    send_email = fields.Boolean(string='Send Email', default=True)
    post_chatter = fields.Boolean(
        string='Post on Record Chatter', default=True,
        help='Post the notification as a message on the related record.',
    )
    create_activity = fields.Boolean(
        string='Create Activity', default=False,
        help='Create a To-Do activity on the employee\'s record.',
    )
    activity_type_id = fields.Many2one(
        'mail.activity.type', string='Activity Type',
    )
    activity_deadline_days = fields.Integer(string='Activity Deadline (days)', default=7)

    # Auto-send via cron
    is_automated = fields.Boolean(
        string='Automated',
        help='When enabled, this notification is sent automatically by the system '
             'when the trigger event occurs. If disabled, it can only be sent manually.',
        default=True,
    )

    # Log
    log_ids = fields.One2many('lms.notification.log', 'template_id', string='Send History')
    log_count = fields.Integer(string='Sent', compute='_compute_log_count')

    @api.depends('log_ids')
    def _compute_log_count(self):
        for rec in self:
            rec.log_count = len(rec.log_ids)

    def _render_body(self, context_values):
        """Replace placeholders in subject and body with actual values."""
        body = self.body_html or ''
        subject = self.subject or ''
        for key, value in context_values.items():
            placeholder = '{{%s}}' % key
            body = body.replace(placeholder, str(value or ''))
            subject = subject.replace(placeholder, str(value or ''))
        return subject, body

    def _get_recipients(self, record):
        """Return a list of res.partner records to notify."""
        partners = self.env['res.partner']
        employee = None

        if hasattr(record, 'employee_id'):
            employee = record.employee_id
        elif record._name == 'hr.employee':
            employee = record

        if self.recipient_type in ('employee', 'both') and employee and employee.user_id:
            partners |= employee.user_id.partner_id
        if self.recipient_type in ('manager', 'both') and employee and employee.parent_id and employee.parent_id.user_id:
            partners |= employee.parent_id.user_id.partner_id
        if self.recipient_type == 'group' and self.recipient_group_id:
            partners |= self.recipient_group_id.users.mapped('partner_id')
        if self.recipient_type == 'custom' and self.recipient_email:
            for email in self.recipient_email.split(','):
                email = email.strip()
                if email:
                    partner = self.env['res.partner'].search([('email', '=', email)], limit=1)
                    if not partner:
                        partner = self.env['res.partner'].create({'name': email, 'email': email})
                    partners |= partner

        return partners

    def _build_context(self, record):
        """Build the placeholder substitution dict from a record."""
        ctx = {
            'employee_name': '',
            'course_name': '',
            'session_name': '',
            'session_date': '',
            'session_location': '',
            'completion_date': '',
            'expiry_date': '',
            'package_name': '',
            'manager_name': '',
        }
        if hasattr(record, 'employee_id') and record.employee_id:
            emp = record.employee_id
            ctx['employee_name'] = emp.name
            if emp.parent_id:
                ctx['manager_name'] = emp.parent_id.name
        if hasattr(record, 'course_id') and record.course_id:
            ctx['course_name'] = record.course_id.name
        if hasattr(record, 'session_id') and record.session_id:
            sess = record.session_id
            ctx['session_name'] = sess.name
            ctx['session_date'] = str(sess.date_start or '')
            ctx['session_location'] = sess.location or ''
        if record._name == 'lms.course.session':
            ctx['session_name'] = record.name
            ctx['session_date'] = str(record.date_start or '')
            ctx['session_location'] = record.location or ''
        if hasattr(record, 'completion_date'):
            ctx['completion_date'] = str(record.completion_date or '')
        if hasattr(record, 'expiry_date'):
            ctx['expiry_date'] = str(record.expiry_date or '')
        if hasattr(record, 'course_group_id') and record.course_group_id:
            ctx['package_name'] = record.course_group_id.name
        return ctx

    def send_notification(self, record):
        """
        Send this notification for the given record.
        Creates a log entry and optionally posts on chatter / creates activity.
        """
        self.ensure_one()
        context_values = self._build_context(record)
        subject, body = self._render_body(context_values)
        partners = self._get_recipients(record)

        if not partners and not self.send_email:
            _logger.warning('LMS Notification %s: no recipients found for record %s,%s',
                            self.name, record._name, record.id)
            return

        # Post on chatter
        if self.post_chatter:
            try:
                record.message_post(
                    body=body,
                    subject=subject,
                    partner_ids=partners.ids,
                    subtype_xmlid='mail.mt_comment',
                )
            except Exception as e:
                _logger.error('LMS Notification chatter post error: %s', e)

        # Send email
        if self.send_email and partners:
            try:
                mail = self.env['mail.mail'].create({
                    'subject': subject,
                    'body_html': body,
                    'recipient_ids': [(6, 0, partners.ids)],
                    'auto_delete': True,
                })
                mail.send()
            except Exception as e:
                _logger.error('LMS Notification email send error: %s', e)

        # Create activity on the employee record if configured
        if self.create_activity and self.activity_type_id:
            employee = None
            if hasattr(record, 'employee_id'):
                employee = record.employee_id
            if employee:
                try:
                    employee.activity_schedule(
                        activity_type_id=self.activity_type_id.id,
                        summary=subject,
                        note=body,
                        date_deadline=fields.Date.today() + fields.Date.today().__class__.today().replace(
                            day=fields.Date.today().day + self.activity_deadline_days
                        ) if self.activity_deadline_days else fields.Date.today(),
                    )
                except Exception as e:
                    _logger.error('LMS Notification activity create error: %s', e)

        # Log
        self.env['lms.notification.log'].create({
            'template_id': self.id,
            'record_model': record._name,
            'record_id': record.id,
            'record_name': record.display_name,
            'subject': subject,
            'recipients': ', '.join(partners.mapped('email') or []),
        })

    def action_send_manual(self, record_ids=None):
        """
        Manually trigger this notification template for selected records.
        record_ids: list of IDs for the trigger_model.
        """
        self.ensure_one()
        if not record_ids:
            raise UserError(_('No records selected to send notifications for.'))
        records = self.env[self.trigger_model].browse(record_ids)
        for record in records:
            self.send_notification(record)

    def action_view_logs(self):
        self.ensure_one()
        return {
            'name': _('Send History — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'lms.notification.log',
            'view_mode': 'list,form',
            'domain': [('template_id', '=', self.id)],
        }

    @api.model
    def _cron_send_session_reminders(self):
        """Cron: send session reminder notifications N days before the session."""
        today = fields.Date.today()
        templates = self.search([
            ('is_automated', '=', True),
            ('trigger_event', '=', 'session_reminder'),
            ('trigger_model', '=', 'lms.course.session'),
        ])
        for template in templates:
            from datetime import timedelta
            target_date = today + timedelta(days=template.reminder_days)
            sessions = self.env['lms.course.session'].search([
                ('date_start', '>=', str(target_date) + ' 00:00:00'),
                ('date_start', '<=', str(target_date) + ' 23:59:59'),
                ('state', '=', 'open'),
            ])
            for session in sessions:
                for enrollment in session.enrollment_ids.filtered(lambda e: e.state == 'confirmed'):
                    # Use enrollment record as context carrier
                    template.send_notification(enrollment)


class LmsNotificationLog(models.Model):
    """History log of sent LMS notifications."""
    _name = 'lms.notification.log'
    _description = 'LMS Notification Log'
    _order = 'create_date desc'
    _rec_name = 'subject'

    template_id = fields.Many2one(
        'lms.notification.template', string='Template',
        ondelete='set null', readonly=True,
    )
    record_model = fields.Char(string='Model', readonly=True)
    record_id = fields.Integer(string='Record ID', readonly=True)
    record_name = fields.Char(string='Record', readonly=True)
    subject = fields.Char(string='Subject', readonly=True)
    recipients = fields.Char(string='Recipients', readonly=True)
    create_date = fields.Datetime(string='Sent At', readonly=True)
    sent_by = fields.Many2one(
        'res.users', string='Sent By',
        default=lambda self: self.env.user,
        readonly=True,
    )

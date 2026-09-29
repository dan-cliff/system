from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext


class EmergencyBroadcast(models.Model):
    _name = 'emergency.broadcast'
    _description = 'Emergency Broadcast'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'
    _check_company_auto = True

    # ── Core fields ──────────────────────────────────────────────────────────
    name = fields.Char('Title', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', 'Company', required=True, tracking=True,
        default=lambda self: self.env.company)
    incident_id = fields.Many2one(
        'incident.report',
        string='Related Incident',
        ondelete='set null',
        tracking=True,
        help='The incident report that triggered this emergency broadcast.',
    )
    message_body = fields.Html('Message', required=True, sanitize=True)
    status_id = fields.Many2one(
        'emergency.broadcast.status', 'Status', required=True, tracking=True,
        ondelete='restrict')
    channel_ids = fields.Many2many(
        'emergency.broadcast.channel',
        'emergency_broadcast_channel_rel',
        'broadcast_id', 'channel_id',
        string='Delivery Channels',
        help='Select one or more channels through which this broadcast will be delivered.')
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Important'),
        ('2', 'Urgent'),
        ('3', 'Critical'),
    ], string='Priority', default='1', required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('complete', 'Complete'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='draft', required=True, tracking=True)
    sent_date = fields.Datetime('Sent Date', readonly=True, tracking=True)
    created_by_id = fields.Many2one(
        'res.users', 'Created By', default=lambda self: self.env.user, readonly=True)
    requested_by_id = fields.Many2one(
        'res.users', 'Requested By', readonly=True, tracking=True,
        help='The user who triggered this broadcast via the Emergency Assistance button. '
             'Empty for manually-created broadcasts.')

    # ── Recipient filter ──────────────────────────────────────────────────────
    recipient_filter = fields.Selection([
        ('all', 'All Internal Users'),
        ('company', 'By Company'),
        ('users', 'Specific Users'),
        ('logged_in', 'Logged-In Users Only'),
    ], string='Recipient Filter', default='all', required=True,
        help='Determines which users will receive this broadcast.')
    company_ids = fields.Many2many(
        'res.company',
        'emergency_broadcast_company_rel',
        'broadcast_id', 'company_id',
        string='Companies',
        help='Used when Recipient Filter is set to "By Company".')
    specific_user_ids = fields.Many2many(
        'res.users',
        'emergency_broadcast_user_rel',
        'broadcast_id', 'user_id',
        string='Specific Users',
        domain=[('share', '=', False), ('active', '=', True)],
        help='Used when Recipient Filter is set to "Specific Users".')

    # ── Recipient tracking ────────────────────────────────────────────────────
    recipient_line_ids = fields.One2many(
        'emergency.broadcast.recipient', 'broadcast_id', 'Recipients')
    total_recipients = fields.Integer(
        'Total Recipients', compute='_compute_stats', store=True)
    total_acknowledged = fields.Integer(
        'Acknowledged', compute='_compute_stats', store=True)
    total_pending = fields.Integer(
        'Pending Acknowledgement', compute='_compute_stats', store=True)
    acknowledgement_rate = fields.Float(
        'Acknowledgement Rate (%)', compute='_compute_stats', store=True)
    requires_acknowledgement = fields.Boolean(
        'Requires Acknowledgement',
        compute='_compute_requires_acknowledgement',
        store=True,
        help='True when at least one delivery channel is a Dialogue Box.')

    # ── Computed helpers ──────────────────────────────────────────────────────
    @api.depends('recipient_line_ids', 'recipient_line_ids.acknowledged')
    def _compute_stats(self):
        for rec in self:
            lines = rec.recipient_line_ids
            total = len(lines)
            ack = lines.filtered('acknowledged')
            rec.total_recipients = total
            rec.total_acknowledged = len(ack)
            rec.total_pending = total - len(ack)
            rec.acknowledgement_rate = (len(ack) / total * 100.0) if total else 0.0

    @api.depends('channel_ids', 'channel_ids.technical_type')
    def _compute_requires_acknowledgement(self):
        for rec in self:
            rec.requires_acknowledgement = any(
                ch.technical_type == 'dialog' for ch in rec.channel_ids
            )

    # ── State transitions ─────────────────────────────────────────────────────
    def action_send(self):
        """Resolve recipients, create recipient lines, and dispatch to each channel."""
        self.ensure_one()
        if self.state in ('sent', 'complete'):
            raise UserError('This broadcast has already been sent.')
        if not self.channel_ids:
            raise UserError('Please select at least one delivery channel before sending.')

        users = self._get_recipient_users()
        if not users:
            raise UserError(
                'No users match the selected recipient filter.  '
                'Please adjust the filter criteria and try again.')

        # Re-create recipient lines each time Send is triggered
        self.recipient_line_ids.unlink()
        now = fields.Datetime.now()
        recipient_vals = [
            {'broadcast_id': self.id, 'user_id': u.id, 'sent_date': now}
            for u in users
        ]
        recipients = self.env['emergency.broadcast.recipient'].create(recipient_vals)

        # Build a mapping user_id → recipient record for bus payloads
        recipient_by_user = {r.user_id.id: r for r in recipients}

        for channel in self.channel_ids:
            if channel.technical_type == 'email':
                self._send_email(users)
            elif channel.technical_type == 'sms':
                self._send_sms(users)
            elif channel.technical_type == 'popup':
                self._send_bus(users, recipient_by_user, 'popup')
            elif channel.technical_type == 'dialog':
                self._send_bus(users, recipient_by_user, 'dialog')

        self.write({'state': 'sent', 'sent_date': now})
        self.message_post(
            body='Broadcast sent to %d recipient(s).' % len(users),
            message_type='comment',
        )

    def action_resolve(self):
        """Mark the broadcast as complete and switch its status to Resolved."""
        self.ensure_one()
        if self.state != 'sent':
            raise UserError('Only sent broadcasts can be resolved.')
        resolved_status = self.env.ref(
            'emergency_broadcast.status_resolved', raise_if_not_found=False)
        vals = {'state': 'complete'}
        if resolved_status:
            vals['status_id'] = resolved_status.id
        self.write(vals)
        self.message_post(
            body='Broadcast marked as resolved.',
            message_type='comment',
        )

    def action_cancel(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('Only draft broadcasts can be cancelled.')
        self.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    # ── Recipient resolution ──────────────────────────────────────────────────
    def _get_recipient_users(self):
        """Return a res.users recordset matching the configured filter."""
        self.ensure_one()
        Users = self.env['res.users']
        base_domain = [('active', '=', True), ('share', '=', False)]

        if self.recipient_filter == 'users':
            return self.specific_user_ids.filtered(lambda u: u.active and not u.share)

        if self.recipient_filter == 'company':
            if not self.company_ids:
                return Users
            base_domain.append(('company_id', 'in', self.company_ids.ids))
            return Users.search(base_domain)

        if self.recipient_filter == 'logged_in':
            logged_in_ids = self.env['emergency.broadcast.user.presence'].get_logged_in_user_ids()
            if not logged_in_ids:
                return Users
            base_domain.append(('id', 'in', logged_in_ids))
            return Users.search(base_domain)

        # default: all internal users
        return Users.search(base_domain)

    # ── Channel dispatch ──────────────────────────────────────────────────────
    def _send_email(self, users):
        """Send the broadcast via Odoo mail."""
        self.ensure_one()
        partners = users.mapped('partner_id')
        if not partners:
            return
        priority_label = dict(self._fields['priority'].selection).get(self.priority, '')
        subject = '[%s] %s' % (priority_label, self.name) if priority_label else self.name
        self.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': self.message_body,
            'recipient_ids': [(6, 0, partners.ids)],
            'auto_delete': True,
        }).send()

    def _send_sms(self, users):
        """Send the broadcast via Odoo SMS."""
        self.ensure_one()
        plain_message = html2plaintext(self.message_body or '')[:160]
        numbers = users.filtered('partner_id.phone').mapped('partner_id.phone')
        if not numbers:
            numbers = users.filtered('partner_id.mobile').mapped('partner_id.mobile')
        for number in numbers:
            self.env['sms.sms'].sudo().create({
                'number': number,
                'body': plain_message,
            }).send()

    def _send_bus(self, users, recipient_by_user, notification_type):
        """Dispatch popup or dialog notifications via the Odoo bus.

        In Odoo 19, bus.bus._sendmany() was removed.  Use _sendone() per recipient.
        """
        self.ensure_one()
        priority_label = dict(self._fields['priority'].selection).get(self.priority, '')
        plain_message = html2plaintext(self.message_body or '')

        Bus = self.env['bus.bus']
        for user in users:
            if not user.partner_id:
                continue
            recipient = recipient_by_user.get(user.id)
            payload = {
                'type': notification_type,
                'broadcast_id': self.id,
                'broadcast_name': self.name,
                'message_html': self.message_body or '',
                'message_plain': plain_message,
                'priority': self.priority,
                'priority_label': priority_label,
                'recipient_id': recipient.id if recipient else False,
            }
            Bus._sendone(user.partner_id, 'emergency_broadcast/notification', payload)

    # ── Permission Management integration ────────────────────────────────────
    @api.model
    def _sync_permission_roles(self):
        """Called from data loading to ensure the 'Generate Emergency Broadcast'
        role is present in the Permission Management role library.

        Runs on every ``odoo-bin -u emergency_broadcast`` so new roles added
        to permission_management.hooks.ROLE_DEFINITIONS are picked up even when
        permission_management is updated before this module.  Safe to call
        repeatedly — the role library is idempotent (skips already-existing roles).

        Does nothing if permission_management is not installed.
        """
        Role = self.env.get('permission.role')
        if Role is not None:
            Role._load_role_library()

    # ── Smart button helpers ──────────────────────────────────────────────────
    def action_view_recipients(self):
        """Open the recipient lines for this broadcast."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Recipients',
            'res_model': 'emergency.broadcast.recipient',
            'view_mode': 'list',
            'domain': [('broadcast_id', '=', self.id)],
            'context': {'default_broadcast_id': self.id},
        }

    # ── Emergency Assistance helper ───────────────────────────────────────────
    @api.model
    def create_from_assistance_button(self):
        """
        Creates and immediately sends an emergency broadcast using the
        settings configured for the Emergency Assistance button.
        Returns the new broadcast ID.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        status_id = int(ICP.get_param('emergency_broadcast.assistance_status_id', default=0) or 0)
        message = ICP.get_param('emergency_broadcast.assistance_message', default='Emergency assistance has been requested.')
        priority = ICP.get_param('emergency_broadcast.assistance_priority', default='3')
        recipient_filter = ICP.get_param('emergency_broadcast.assistance_recipient_filter', default='all')
        channel_ids_str = ICP.get_param('emergency_broadcast.assistance_channel_ids', default='')

        # Resolve status
        status = self.env['emergency.broadcast.status'].browse(status_id) if status_id else False
        if not status or not status.exists():
            status = self.env['emergency.broadcast.status'].search([], limit=1)
        if not status:
            raise UserError(
                'No Emergency Broadcast Status is configured.  '
                'Please set up a status in Emergency Broadcast → Configuration → Statuses.')

        # Resolve channels
        channel_ids = []
        if channel_ids_str:
            try:
                channel_ids = [int(x) for x in channel_ids_str.split(',') if x.strip()]
            except (ValueError, TypeError):
                pass
        if not channel_ids:
            channels = self.env['emergency.broadcast.channel'].search([], limit=1)
            channel_ids = channels.ids

        # Build the message body — include requesting user details
        user = self.env.user
        body = (
            '<p><strong>Emergency Assistance Request</strong></p>'
            '<p>%s</p>'
            '<p><em>Requested by: %s</em></p>'
        ) % (message, user.name)

        broadcast = self.create({
            'name': 'Emergency Assistance Request',
            'message_body': body,
            'status_id': status.id,
            'channel_ids': [(6, 0, channel_ids)],
            'priority': priority,
            'recipient_filter': recipient_filter,
            'requested_by_id': user.id,
        })
        broadcast.action_send()
        return broadcast.id

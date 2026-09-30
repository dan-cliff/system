import base64
import email
import email.policy
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import email_normalize, email_normalize_all
from odoo.tools.mail import unfold_references

_logger = logging.getLogger(__name__)


class MandrillMailLog(models.Model):
    _name = 'mandrill.mail.log'
    _description = 'Mailchimp Transactional Email Log'
    _order = 'date desc, id desc'
    _rec_name = 'subject'

    date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True, index=True)
    # direction and state are technical values the send/receive code relies on
    direction = fields.Selection(
        [('outbound', 'Sent'), ('inbound', 'Received')],
        required=True, readonly=True, index=True)
    state = fields.Selection([
        ('queued', 'Queued'),
        ('scheduled', 'Scheduled'),
        ('sent', 'Sent'),
        ('deferred', 'Deferred'),
        ('soft_bounced', 'Soft Bounced'),
        ('bounced', 'Bounced'),
        ('spam', 'Marked as Spam'),
        ('rejected', 'Rejected'),
        ('invalid', 'Invalid'),
        ('error', 'Error'),
        ('received', 'Received'),
        ('processed', 'Processed'),
        ('ignored', 'Ignored'),
        ('failed', 'Failed'),
    ], required=True, readonly=True, index=True)
    subject = fields.Char(readonly=True)
    email_from = fields.Char('From', readonly=True)
    email_to = fields.Char('To', readonly=True)
    email_cc = fields.Char('Cc', readonly=True)
    reply_to = fields.Char('Reply-To', readonly=True)
    recipient = fields.Char(
        readonly=True, help="Address the email was sent to (sent) or the inbound route it matched (received).")
    message_id = fields.Char('Message-Id', readonly=True, index='btree_not_null')
    in_reply_to = fields.Char('In-Reply-To', readonly=True)
    references = fields.Text(readonly=True)
    mandrill_id = fields.Char('Mailchimp Message ID', readonly=True, index='btree_not_null')
    reply_token = fields.Char(
        readonly=True, index='btree_not_null',
        help="Token added to the reply-to address so a reply can be matched back to this email's record.")
    res_model = fields.Char('Related Model', readonly=True, index=True)
    res_id = fields.Many2oneReference('Related Record ID', model_field='res_model', readonly=True)
    record_name = fields.Char('Related Record', compute='_compute_record_name')
    mail_message_id = fields.Many2one('mail.message', 'Chatter Message', readonly=True, ondelete='set null')
    source_log_id = fields.Many2one(
        'mandrill.mail.log', 'Replying To', readonly=True, ondelete='set null',
        help="The sent email this received email was matched to.")
    metadata = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)
    raw_message = fields.Binary('Raw Email', attachment=True, readonly=True)
    open_count = fields.Integer('Opens', readonly=True)
    click_count = fields.Integer('Clicks', readonly=True)
    last_event = fields.Char(readonly=True)
    last_event_date = fields.Datetime(readonly=True)

    @api.depends('res_model', 'res_id')
    def _compute_record_name(self):
        for log in self:
            record = log._get_record()
            log.record_name = record.display_name if record else False

    def _get_record(self):
        self.ensure_one()
        if not (self.res_model and self.res_id) or self.res_model not in self.env:
            return None
        return self.env[self.res_model].sudo().browse(self.res_id).exists() or None

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def action_open_record(self):
        self.ensure_one()
        if not self._get_record():
            raise UserError(_("The related record no longer exists."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_reprocess(self):
        inbound = self.filtered(lambda log: log.direction == 'inbound' and log.state in ('failed', 'ignored', 'received'))
        if not inbound:
            raise UserError(_("Only received emails that failed or were ignored can be processed again."))
        inbound.write({'state': 'received', 'error_message': False})
        inbound._process_inbound()
        return True

    # ------------------------------------------------------------
    # Inbound processing
    # ------------------------------------------------------------

    @api.model
    def _cron_process_inbound(self, limit=100):
        logs = self.search([('direction', '=', 'inbound'), ('state', '=', 'received')], order='id', limit=limit)
        logs._process_inbound()
        remaining = self.search_count([('direction', '=', 'inbound'), ('state', '=', 'received')])
        if remaining:
            self.env.ref('mandrill_mail.ir_cron_mandrill_process_inbound')._trigger()

    def _process_inbound(self):
        """Hand each received email to Odoo's mail gateway
        (``mail.thread.message_process``), the same entry point incoming
        mail servers use, so aliases, replies and bounces behave as usual."""
        service = self.env['mandrill.service']
        for log in self:
            try:
                with self.env.cr.savepoint():
                    log._process_inbound_one(service)
            except Exception as e:  # noqa: BLE001 - keep the error on the log and move on
                _logger.info("Mailchimp Transactional: could not process inbound email %s: %s", log.message_id, e)
                log.write({'state': 'failed', 'error_message': str(e)})

    def _process_inbound_one(self, service):
        self.ensure_one()
        raw = base64.b64decode(self.raw_message or b'')
        if not raw:
            self.write({'state': 'failed', 'error_message': _("The email has no content.")})
            return
        raw = self._add_delivered_to(raw)

        source = self._find_source_log(service)
        model, thread_id = (source.res_model, source.res_id) if source and source.res_model else (False, None)
        MailThread = self.env['mail.thread'].sudo()
        if source and source.reply_token and source.reply_token in service._find_reply_tokens(
                self.recipient, self.email_to):
            # The reply came back through the tokenized reply-to: attach it to
            # the record the original email was sent from.
            MailThread = MailThread.with_context(mandrill_force_thread=(model, thread_id))
        MailThread.message_process(model, raw, thread_id=thread_id)

        message = self.env['mail.message'].sudo().search(
            [('message_id', '=', self.message_id)], order='id desc', limit=1) if self.message_id else None
        if message:
            self.write({
                'state': 'processed',
                'mail_message_id': message.id,
                'res_model': message.model,
                'res_id': message.res_id,
                'source_log_id': source.id if source else False,
                'error_message': False,
            })
        else:
            self.write({
                'state': 'ignored',
                'source_log_id': source.id if source else False,
                'error_message': _(
                    "Odoo's mail gateway did not post this email on any record: it is a bounce, "
                    "an auto-reply loop or a duplicate of an email already received."),
            })

    def _find_source_log(self, service):
        """The sent email this one replies to: first by reply tracking token,
        then by the In-Reply-To / References headers."""
        Log = self.sudo()
        tokens = service._find_reply_tokens(self.recipient, self.email_to)
        if tokens:
            source = Log.search([('direction', '=', 'outbound'), ('reply_token', 'in', tokens)],
                                order='id desc', limit=1)
            if source:
                return source
        references = [r.strip() for r in unfold_references(self.references or self.in_reply_to or '') if r.strip()]
        if references:
            return Log.search([
                ('direction', '=', 'outbound'), ('message_id', 'in', references[-32:]), ('res_model', '!=', False),
            ], order='id desc', limit=1)
        return Log

    def _add_delivered_to(self, raw):
        """Mandrill passes the original message untouched. When the route
        address isn't in To/Cc (e.g. it was Bcc'd), add a Delivered-To header
        so Odoo's alias matching sees which address received it."""
        recipient = email_normalize(self.recipient or '')
        if not recipient:
            return raw
        message = email.message_from_bytes(raw, policy=email.policy.SMTP)
        if message.get_all('Delivered-To'):
            return raw
        visible = email_normalize_all(', '.join(
            str(v) for v in (message.get_all('To') or []) + (message.get_all('Cc') or [])))
        if recipient in visible:
            return raw
        return f'Delivered-To: {recipient}\r\n'.encode() + raw

    # ------------------------------------------------------------
    # Bounces and housekeeping
    # ------------------------------------------------------------

    def _handle_hard_bounce(self, bounced_email, reason):
        """Feed a Mandrill hard bounce into Odoo's own bounce handling so the
        contact's bounce counter and the message's notification update, just
        like a bounce email received by the bounce alias would."""
        self.ensure_one()
        bounced_email = email_normalize(bounced_email or '')
        if not bounced_email:
            return
        partner = self.env['res.partner'].sudo().search([('email_normalized', '=', bounced_email)], limit=1)
        self.env['mail.thread'].sudo()._routing_handle_bounce(None, {
            'bounced_email': bounced_email,
            'bounced_partner': partner,
            'bounced_msg_ids': [self.message_id] if self.message_id else [],
            'bounced_message': self.mail_message_id.sudo(),
            'email_from': 'Mailchimp Transactional',
            'to': bounced_email,
            'message_id': self.message_id,
            'body': reason or '',
        })

    @api.model
    def _cron_gc_logs(self):
        days = int(self.env['mandrill.service']._get_param('log_retention_days') or 0)
        if days <= 0:
            return
        limit_date = fields.Datetime.now() - timedelta(days=days)
        self.search([('date', '<', limit_date), ('state', '!=', 'received')]).unlink()

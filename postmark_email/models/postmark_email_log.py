import base64
import email
import email.policy
import json
import logging
import re
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.mail import email_normalize

from .postmark_api import PARAM_BLACKLIST_SPAM, parse_postmark_datetime

_logger = logging.getLogger(__name__)

# Headers rebuilt from Postmark's own JSON fields (or which only describe the
# original MIME layout) when turning an inbound payload back into an email.
INBOUND_SKIP_HEADERS = {
    'from', 'to', 'cc', 'bcc', 'subject', 'date', 'reply-to', 'message-id',
    'mime-version', 'content-type', 'content-transfer-encoding',
}


class PostmarkEmailLog(models.Model):
    _name = 'postmark.email.log'
    _description = 'Postmark Email Log'
    _order = 'date desc, id desc'
    _rec_name = 'subject'

    # direction and state are technical: the webhook code sets them and
    # filters on these exact values.
    direction = fields.Selection(
        [('outgoing', 'Outgoing'), ('incoming', 'Incoming')],
        required=True, readonly=True, index=True)
    state = fields.Selection(
        [('sent', 'Sent'),
         ('delivered', 'Delivered'),
         ('soft_bounce', 'Soft Bounce'),
         ('bounced', 'Bounced'),
         ('spam', 'Spam Complaint'),
         ('failed', 'Failed'),
         ('received', 'Received'),
         ('unrouted', 'Not Routed'),
         ('error', 'Processing Error')],
        required=True, readonly=True, index=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True, index=True)
    subject = fields.Char(readonly=True)
    email_from = fields.Char(string='From', readonly=True)
    email_to = fields.Char(string='To', readonly=True)
    email_cc = fields.Char(string='Cc', readonly=True)
    email_bcc = fields.Char(string='Bcc', readonly=True)
    reply_to = fields.Char(string='Reply-To', readonly=True)
    stream_id = fields.Many2one('postmark.message.stream', string='Message Stream', readonly=True)
    postmark_message_id = fields.Char(string='Postmark Message ID', readonly=True, index=True)
    message_id = fields.Char(string='Message-ID', readonly=True, index=True,
                             help="The email's Message-ID header.")
    res_model = fields.Char(string='Document Model', readonly=True, index=True)
    res_id = fields.Many2oneReference(string='Document ID', model_field='res_model', readonly=True)
    record_name = fields.Char(compute='_compute_record_name')
    mail_message_id = fields.Many2one('mail.message', string='Odoo Message', readonly=True,
                                      ondelete='set null', index='btree_not_null')
    error = fields.Text(readonly=True)
    event_date = fields.Datetime(string='Event Date', readonly=True,
                                 help="When Postmark reported the delivery, bounce or spam complaint.")
    event_type = fields.Char(string='Bounce Type', readonly=True,
                             help="Postmark's bounce type, e.g. HardBounce, SoftBounce or SpamComplaint.")
    event_details = fields.Text(string='Event Details', readonly=True)
    payload = fields.Text(readonly=True, help="The JSON Postmark sent for an incoming email.")

    @api.depends('res_model', 'res_id')
    def _compute_record_name(self):
        for log in self:
            name = False
            if log.res_model in self.env and log.res_id:
                record = self.env[log.res_model].sudo().browse(log.res_id).exists()
                name = record.display_name if record else False
            log.record_name = name

    def action_open_record(self):
        self.ensure_one()
        if not (self.res_model in self.env and self.res_id):
            raise UserError(_("This email isn't linked to a record."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_retry_inbound(self):
        """Process a stored incoming email again (e.g. after adding an alias)."""
        for log in self:
            if log.direction != 'incoming' or not log.payload:
                raise UserError(_("Only incoming emails with a stored payload can be processed again."))
            log._postmark_process_inbound_payload(json.loads(log.payload))
        return True

    # ------------------------------------------------------------------
    # Incoming email
    # ------------------------------------------------------------------

    @api.model
    def _postmark_receive_inbound(self, payload):
        """Log and process one inbound webhook payload from Postmark."""
        log = self.create({
            'direction': 'incoming',
            'state': 'received',
            'subject': payload.get('Subject'),
            'email_from': self._postmark_format_from(payload),
            'email_to': payload.get('To'),
            'email_cc': payload.get('Cc'),
            'email_bcc': payload.get('Bcc'),
            'reply_to': payload.get('ReplyTo'),
            'postmark_message_id': payload.get('MessageID'),
            'message_id': self._postmark_header(payload, 'Message-ID'),
            'stream_id': self.env['postmark.message.stream'].search(
                [('stream_id', '=', payload.get('MessageStream') or 'inbound')], limit=1).id,
            'date': parse_postmark_datetime(payload.get('Date')) or fields.Datetime.now(),
            'payload': json.dumps(payload),
        })
        log._postmark_process_inbound_payload(payload)
        return log

    def _postmark_process_inbound_payload(self, payload):
        self.ensure_one()
        model, thread_id = self._postmark_inbound_target(payload)
        raw = self._postmark_inbound_raw(payload)
        vals = {'state': 'received', 'error': False}
        try:
            with self.env.cr.savepoint():
                self.env['mail.thread'].message_process(model, raw, thread_id=thread_id)
        except ValueError as e:
            # message_route raises ValueError when no alias or record matches
            _logger.info("Postmark: inbound email %s not routed: %s", payload.get('MessageID'), e)
            vals.update(state='unrouted', error=str(e))
        except Exception as e:  # noqa: BLE001 - keep the payload so it can be retried
            _logger.exception("Postmark: failed to process inbound email %s", payload.get('MessageID'))
            vals.update(state='error', error=str(e))
        parsed = email.message_from_bytes(raw, policy=email.policy.SMTP)
        message_id = (parsed['Message-ID'] or '').strip()
        mail_message = self.env['mail.message'].sudo().search(
            [('message_id', '=', message_id)], limit=1) if message_id else False
        if mail_message:
            vals.update(mail_message_id=mail_message.id, res_model=mail_message.model,
                        res_id=mail_message.res_id)
        elif model and thread_id:
            vals.update(res_model=model, res_id=thread_id)
        vals['message_id'] = message_id or self.message_id
        self.write(vals)

    @api.model
    def _postmark_inbound_target(self, payload):
        """Work out which record a reply belongs to.

        1. The reply token in the address's mailbox hash (``reply+token@``),
           added to the Reply-To of emails sent from records.
        2. The In-Reply-To / References headers, matched against the
           Message-IDs we logged when sending (Postmark gives sent emails its
           own Message-ID, which Odoo alone wouldn't recognise).

        Returns ``(model, res_id)`` or ``(None, None)`` to leave the routing
        to Odoo's aliases.
        """
        Api = self.env['postmark.api']
        hashes = [payload.get('MailboxHash')]
        hashes += [r.get('MailboxHash') for r in (payload.get('ToFull') or []) + (payload.get('CcFull') or [])]
        for mailbox_hash in filter(None, hashes):
            model, res_id = Api._parse_record_token(mailbox_hash)
            if model:
                return model, res_id

        references = ' '.join(filter(None, [
            self._postmark_header(payload, 'In-Reply-To'),
            self._postmark_header(payload, 'References'),
        ]))
        message_ids = re.findall(r'<[^<>\s]+>', references)
        if message_ids:
            local_parts = [m[1:-1].split('@')[0] for m in message_ids]
            sent = self.sudo().search([
                ('direction', '=', 'outgoing'),
                ('res_model', '!=', False),
                '|', ('message_id', 'in', message_ids),
                ('postmark_message_id', 'in', local_parts),
            ], order='id desc', limit=1)
            if sent and sent.res_model in self.env and self.env[sent.res_model].browse(sent.res_id).exists():
                return sent.res_model, sent.res_id
        return None, None

    @api.model
    def _postmark_header(self, payload, name):
        name = name.lower()
        for header in payload.get('Headers') or []:
            if (header.get('Name') or '').lower() == name:
                return header.get('Value')
        return False

    @api.model
    def _postmark_format_from(self, payload):
        full = payload.get('FromFull') or {}
        address = full.get('Email') or payload.get('From') or ''
        name = full.get('Name') or payload.get('FromName') or ''
        return formataddr((name, address)) if name and address else address

    @api.model
    def _postmark_inbound_raw(self, payload):
        """Return the inbound email as RFC 2822 bytes for Odoo's mail gateway.

        Uses the original message when Postmark includes it (RawEmail, turned
        on by "Sync with Postmark"), else rebuilds it from the JSON fields.
        """
        if payload.get('RawEmail'):
            return payload['RawEmail'].encode('utf-8', errors='surrogateescape')

        msg = EmailMessage(policy=email.policy.SMTP)
        for header in payload.get('Headers') or []:
            name, value = header.get('Name'), header.get('Value')
            if not name or value is None or name.lower() in INBOUND_SKIP_HEADERS:
                continue
            try:
                msg[name] = value
            except (ValueError, TypeError):
                continue
        msg['From'] = self._postmark_format_from(payload)
        if payload.get('To'):
            msg['To'] = payload['To']
        if payload.get('Cc'):
            msg['Cc'] = payload['Cc']
        if payload.get('ReplyTo'):
            msg['Reply-To'] = payload['ReplyTo']
        msg['Subject'] = payload.get('Subject') or ''
        if payload.get('Date'):
            msg['Date'] = payload['Date']
        msg['Message-ID'] = (self._postmark_header(payload, 'Message-ID')
                             or (f"<{payload['MessageID']}@inbound.postmarkapp.com>"
                                 if payload.get('MessageID') else make_msgid()))

        msg.set_content(payload.get('TextBody') or '')
        if payload.get('HtmlBody'):
            msg.add_alternative(payload['HtmlBody'], subtype='html')
        for attachment in payload.get('Attachments') or []:
            content = base64.b64decode(attachment.get('Content') or '')
            maintype, _sep, subtype = (attachment.get('ContentType') or 'application/octet-stream').partition('/')
            content_id = (attachment.get('ContentID') or '').removeprefix('cid:').strip('<>')
            msg.add_attachment(
                content, maintype=maintype, subtype=subtype or 'octet-stream',
                filename=attachment.get('Name') or 'attachment',
                cid=f'<{content_id}>' if content_id else None)
        return msg.as_bytes()

    # ------------------------------------------------------------------
    # Delivery, bounce and spam complaint webhooks
    # ------------------------------------------------------------------

    @api.model
    def _postmark_receive_event(self, payload):
        record_type = payload.get('RecordType')
        if record_type == 'Delivery':
            return self._postmark_receive_delivery(payload)
        if record_type in ('Bounce', 'SpamComplaint'):
            return self._postmark_receive_bounce(payload)
        return self.browse()

    @api.model
    def _postmark_find_sent(self, payload):
        postmark_id = payload.get('MessageID')
        if not postmark_id:
            return self.browse()
        return self.search([('direction', '=', 'outgoing'),
                            ('postmark_message_id', '=', postmark_id)], limit=1)

    @api.model
    def _postmark_receive_delivery(self, payload):
        log = self._postmark_find_sent(payload)
        if log and log.state == 'sent':
            log.write({
                'state': 'delivered',
                'event_date': parse_postmark_datetime(payload.get('DeliveredAt')),
                'event_details': payload.get('Details'),
            })
        return log

    @api.model
    def _postmark_receive_bounce(self, payload):
        """Flag a bounced / spam-reported email on its log and on the record.

        Postmark marks the address Inactive for hard bounces and spam
        complaints (it will not email it again); only those are passed on to
        Odoo's bounce handling. Soft bounces (e.g. mailbox full) are logged.
        """
        is_spam = payload.get('RecordType') == 'SpamComplaint'
        bounced_email = email_normalize(payload.get('Email') or '') or payload.get('Email')
        metadata = payload.get('Metadata') or {}
        log = self._postmark_find_sent(payload)
        if not log:
            log = self.create({
                'direction': 'outgoing',
                'state': 'sent',
                'subject': payload.get('Subject'),
                'email_from': payload.get('From'),
                'email_to': payload.get('Email'),
                'postmark_message_id': payload.get('MessageID'),
                'stream_id': self.env['postmark.message.stream'].search(
                    [('stream_id', '=', payload.get('MessageStream'))], limit=1).id,
                'res_model': metadata.get('odoo_model') or False,
                'res_id': int(metadata['odoo_res_id']) if str(metadata.get('odoo_res_id', '')).isdigit() else False,
            })
        hard = is_spam or payload.get('Inactive')
        log.write({
            'state': 'spam' if is_spam else ('bounced' if hard else 'soft_bounce'),
            'event_type': payload.get('Type') or payload.get('RecordType'),
            'event_date': parse_postmark_datetime(payload.get('BouncedAt')) or fields.Datetime.now(),
            'event_details': '\n'.join(filter(None, [payload.get('Description'), payload.get('Details')])),
        })
        if hard and bounced_email:
            log._postmark_flag_bounce(bounced_email, is_spam, payload)
        return log

    def _postmark_flag_bounce(self, bounced_email, is_spam, payload):
        self.ensure_one()
        partners = self.env['res.partner'].sudo().search([('email_normalized', '=', bounced_email)])
        mail_message = self.mail_message_id
        if not mail_message:
            odoo_message = str((payload.get('Metadata') or {}).get('odoo_message', ''))
            if odoo_message.isdigit():
                mail_message = self.env['mail.message'].sudo().browse(int(odoo_message)).exists()
        description = payload.get('Description') or payload.get('Type') or ''
        # Odoo's own bounce handling: bumps the bounce counter on every
        # blacklist-enabled record with this address and marks the message's
        # notification to it as bounced (the red envelope in the chatter).
        self.env['mail.thread'].sudo()._routing_handle_bounce(None, {
            'bounced_email': bounced_email,
            'bounced_partner': partners,
            'bounced_msg_ids': [self.message_id] if self.message_id else [],
            'bounced_message': mail_message or self.env['mail.message'],
            'body': description,
            'email_from': payload.get('From'),
            'to': payload.get('Email'),
            'message_id': self.message_id,
        })
        if is_spam and self.env['postmark.api']._get_param(PARAM_BLACKLIST_SPAM):
            self.env['mail.blacklist'].sudo()._add(
                bounced_email, message=_("Marked an email as spam (reported by Postmark)."))

        record = self._postmark_record()
        if record is not None and hasattr(record, 'message_post'):
            if is_spam:
                body = _("%(email)s marked the email \"%(subject)s\" as spam.",
                         email=bounced_email, subject=self.subject or '')
            else:
                body = _("The email \"%(subject)s\" to %(email)s bounced: %(reason)s",
                         email=bounced_email, subject=self.subject or '', reason=description)
            record.sudo().message_post(
                body=Markup('<p>%s</p>') % body, subtype_xmlid='mail.mt_note',
                message_type='notification')

    def _postmark_record(self):
        self.ensure_one()
        if self.res_model in self.env and self.res_id:
            record = self.env[self.res_model].sudo().browse(self.res_id).exists()
            if record:
                return record
        return None

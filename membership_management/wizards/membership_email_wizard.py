# -*- coding: utf-8 -*-
import base64
import logging

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MembershipEmailWizard(models.TransientModel):
    _name = 'membership.email.wizard'
    _description = 'Membership Email Wizard'

    # ── Context ──────────────────────────────────────────────────────────
    membership_id = fields.Many2one(
        'membership.membership',
        string='Membership',
        required=True,
        ondelete='cascade',
    )

    # ── Template ─────────────────────────────────────────────────────────
    template_id = fields.Many2one(
        'membership.email.template',
        string='Email Template',
        help='Select a template to pre-populate the subject and body.',
    )

    # ── Recipient ─────────────────────────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner',
        string='Recipient',
    )

    # ── Email Content ─────────────────────────────────────────────────────
    subject = fields.Char(string='Subject', required=True)
    body_html = fields.Html(string='Body', sanitize=False)

    # ── Attachments ───────────────────────────────────────────────────────
    manual_attachment_ids = fields.Many2many(
        'ir.attachment',
        'membership_email_wiz_manual_att_rel',
        'wizard_id', 'attachment_id',
        string='Additional Attachments',
        help='Upload or drag-drop extra files to attach to this email.',
    )

    include_membership_card_pdf = fields.Boolean(
        string='Include Membership Card PDF',
        default=False,
    )

    # ── Defaults / Onchange ───────────────────────────────────────────────

    @api.model
    def default_get(self, field_names):
        res = super().default_get(field_names)
        membership_id = res.get('membership_id') or self.env.context.get('default_membership_id')
        if membership_id:
            membership = self.env['membership.membership'].browse(membership_id)
            if membership.exists() and 'partner_id' not in res:
                res['partner_id'] = membership.partner_id.id
        return res

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if not self.template_id or not self.membership_id:
            return
        tmpl = self.template_id
        subj, body = tmpl._render_for_membership(self.membership_id)
        self.subject = subj
        self.body_html = body
        self.manual_attachment_ids = tmpl.attachment_ids

    # ── PDF helper ────────────────────────────────────────────────────────

    def _generate_pdf_attachment(self, report_ref, filename):
        """Render a QWeb report to PDF and return a temporary ir.attachment."""
        try:
            Report = self.env['ir.actions.report']
            pdf_bytes, _ = Report._render_qweb_pdf(
                report_ref, res_ids=[self.membership_id.id]
            )
            return self.env['ir.attachment'].create({
                'name': filename,
                'type': 'binary',
                'datas': base64.b64encode(pdf_bytes),
                'mimetype': 'application/pdf',
            })
        except Exception as e:
            _logger.warning('Could not generate PDF %s: %s', report_ref, e)
            return None

    # ── Send ─────────────────────────────────────────────────────────────

    def action_send_email(self):
        self.ensure_one()

        # ── Resolve recipient ───────────────────────────────────────────
        recipient_partner = self.partner_id
        email_to = (self.partner_id.email or '') if self.partner_id else ''
        recipient_display = (
            f'{self.partner_id.name} &lt;{email_to}&gt;'
            if self.partner_id else email_to
        )

        if not email_to:
            raise UserError(_(
                'The selected recipient has no email address. '
                'Please add one before sending.'
            ))

        # ── Gather attachment IDs ───────────────────────────────────────
        attachment_ids = list(self.manual_attachment_ids.ids)

        if self.include_membership_card_pdf:
            att = self._generate_pdf_attachment(
                'membership_management.action_report_membership_card',
                f'Membership Card - {self.membership_id.name}.pdf',
            )
            if att:
                attachment_ids.append(att.id)

        # ── Create and send mail ────────────────────────────────────────
        mail_vals = {
            'subject': self.subject,
            'body_html': self.body_html or '',
            'email_to': email_to,
            'author_id': self.env.user.partner_id.id,
            'auto_delete': False,
        }
        if recipient_partner:
            mail_vals['recipient_ids'] = [(4, recipient_partner.id)]
        if attachment_ids:
            mail_vals['attachment_ids'] = [(4, aid) for aid in attachment_ids]

        mail = self.env['mail.mail'].create(mail_vals)
        mail.send()

        # ── Log to chatter ──────────────────────────────────────────────
        body_safe = Markup(self.body_html) if self.body_html else Markup('')
        chatter_body = Markup(
            '<div style="font-family:Arial,sans-serif;font-size:13px;">'
            '<p><strong>Email Sent</strong></p>'
            '<table style="border-collapse:collapse;margin-bottom:10px;">'
            '<tr><td style="padding:3px 8px;color:#666;width:70px;">To:</td>'
            '<td style="padding:3px 8px;">{recipient}</td></tr>'
            '<tr><td style="padding:3px 8px;color:#666;">Subject:</td>'
            '<td style="padding:3px 8px;"><strong>{subject}</strong></td></tr>'
            '</table>'
            '<hr style="border:0;border-top:1px solid #eee;margin:8px 0;"/>'
            '{body}'
            '</div>'
        ).format(
            recipient=Markup(recipient_display),
            subject=escape(self.subject or ''),
            body=body_safe,
        )

        self.membership_id.message_post(
            body=chatter_body,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

        return {'type': 'ir.actions.act_window_close'}

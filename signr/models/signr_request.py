# -*- coding: utf-8 -*-
import base64
import hashlib
import logging
import uuid

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.misc import clean_context
from odoo.tools.pdf import merge_pdf

_logger = logging.getLogger(__name__)

# The request's workflow: the signing page and the emails depend on these values.
REQUEST_STATES = [
    ('draft', 'Draft'),
    ('sent', 'Waiting for Signatures'),
    ('signed', 'Signed'),
    ('declined', 'Declined'),
    ('expired', 'Expired'),
    ('cancelled', 'Cancelled'),
]
# A signer's progress: the signing page depends on these values.
SIGNER_STATES = [
    ('draft', 'Not Sent'),
    ('waiting', 'Waiting for Others'),
    ('sent', 'Awaiting Signature'),
    ('signed', 'Signed'),
    ('declined', 'Declined'),
    ('cancelled', 'Cancelled'),
]
ORG_FIELDS = ('org_division_id', 'org_business_unit_id', 'org_location_id', 'org_department_id')


class SignrRequest(models.Model):
    _name = 'signr.request'
    _description = "Sign'r Sign Request"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_names_search = ['name', 'title', 'res_name']
    # New requests take the Organisation units of the record they are raised
    # from (see create), not those of the template.
    _org_parent_field = False

    name = fields.Char('Reference', readonly=True, copy=False, default='/', index=True)
    title = fields.Char('Document', compute='_compute_title', store=True, readonly=False,
                        tracking=True)
    template_id = fields.Many2one(
        'signr.template', string='Template', required=True, tracking=True, index=True, ondelete='restrict',
        domain="[('company_id', 'in', (company_id, False))]")
    document_type_id = fields.Many2one(related='template_id.document_type_id', store=True)
    user_id = fields.Many2one('res.users', string='Sender', required=True, tracking=True, index=True,
                              default=lambda self: self.env.user,
                              domain="[('share', '=', False)]")
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True,
                                 default=lambda self: self.env.company, tracking=True)

    # The record the request was raised from
    app_id = fields.Many2one('ir.module.module', string='App', compute='_compute_source', store=True,
                             readonly=True)
    res_model = fields.Char('Source Model Name', index=True)
    res_model_id = fields.Many2one('ir.model', string='Source Model', compute='_compute_source', store=True,
                                   readonly=True, ondelete='set null')
    res_id = fields.Many2oneReference('Source Record ID', model_field='res_model', index=True)
    res_reference = fields.Reference(selection='_selection_res_reference', string='Source Record',
                                     compute='_compute_res_reference', inverse='_inverse_res_reference')
    res_name = fields.Char('Source Record Name', compute='_compute_source', store=True, readonly=True)

    state = fields.Selection(REQUEST_STATES, string='Status', default='draft', required=True, tracking=True,
                             copy=False, index=True)
    signer_ids = fields.One2many('signr.request.signer', 'request_id', string='Signers', copy=True)
    recipient_names = fields.Char('Sent To', compute='_compute_recipient_names', store=True)
    sign_in_order = fields.Boolean('Sign in Order', default=True)
    expiry_date = fields.Date('Sign Before', tracking=True, copy=False)
    sent_date = fields.Datetime('Sent On', readonly=True, copy=False, tracking=True)
    signed_date = fields.Datetime('Signed On', readonly=True, copy=False, tracking=True)
    email_subject = fields.Char('Email Subject')
    email_message = fields.Html('Email Message')

    document_docx = fields.Binary('Word Document', attachment=True, readonly=True, copy=False)
    document_docx_filename = fields.Char(compute='_compute_filenames')
    document_pdf = fields.Binary('Document to Sign', attachment=True, readonly=True, copy=False)
    document_pdf_filename = fields.Char(compute='_compute_filenames')
    document_hash = fields.Char('Document Fingerprint (SHA-256)', readonly=True, copy=False,
                                help='The fingerprint of the PDF the signers were sent. Any change to '
                                     'the document changes it.')
    signed_pdf = fields.Binary('Signed Document', attachment=True, readonly=True, copy=False)
    signed_pdf_filename = fields.Char(compute='_compute_filenames')

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('template_id', 'res_name')
    def _compute_title(self):
        for request in self:
            if request.template_id:
                request.title = (f'{request.template_id.name} – {request.res_name}' if request.res_name
                                 else request.template_id.name)

    @api.depends('res_model', 'res_id', 'template_id')
    def _compute_source(self):
        for request in self:
            model = self.env['ir.model'].sudo()._get(request.res_model) if request.res_model else False
            request.res_model_id = model
            request.app_id = request.template_id.app_id
            record = request._signr_record()
            request.res_name = record.sudo().display_name if record else False

    @api.depends('res_model', 'res_id')
    def _compute_res_reference(self):
        for request in self:
            request.res_reference = (f'{request.res_model},{request.res_id}'
                                     if request.res_model and request.res_id and request.res_model in self.env
                                     else False)

    def _inverse_res_reference(self):
        for request in self:
            if request.res_reference:
                request.res_model = request.res_reference._name
                request.res_id = request.res_reference.id
            else:
                request.res_model = request.template_id.model_name or False
                request.res_id = False

    @api.model
    def _selection_res_reference(self):
        templates = self.env['signr.template'].sudo().search([])
        models_ = templates.model_id.filtered(lambda m: m.model in self.env)
        return [(model.model, model.name) for model in models_.sorted('name')]

    @api.depends('signer_ids.partner_id')
    def _compute_recipient_names(self):
        for request in self:
            request.recipient_names = ', '.join(request.signer_ids.partner_id.mapped('display_name'))

    @api.depends('name', 'title')
    def _compute_filenames(self):
        for request in self:
            base = (request.title or request.name or 'document').replace('/', '-')
            request.document_docx_filename = f'{base}.docx'
            request.document_pdf_filename = f'{base}.pdf'
            request.signed_pdf_filename = f'{base} (signed).pdf'

    def _compute_display_name(self):
        for request in self:
            request.display_name = f'{request.name} – {request.title}' if request.title else request.name

    # ------------------------------------------------------------------
    # Source record
    # ------------------------------------------------------------------
    def _signr_record(self):
        self.ensure_one()
        if not self.res_model or not self.res_id or self.res_model not in self.env:
            return None
        return self.env[self.res_model].sudo().browse(self.res_id).exists() or None

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        model = values.get('res_model') or self.env.context.get('default_res_model')
        if model and not values.get('template_id') and 'template_id' in fields_list:
            templates = self.env['signr.template'].search(
                [('model_name', '=', model), ('company_id', 'in', (self.env.company.id, False))])
            if len(templates) == 1:
                values['template_id'] = templates.id
        return values

    @api.onchange('template_id')
    def _onchange_template_id(self):
        template = self.template_id
        if not template:
            return
        if self.res_model and self.res_model != template.model_name:
            self.res_model, self.res_id = template.model_name, False
        elif not self.res_model:
            self.res_model = template.model_name
        self.sign_in_order = template.sign_in_order
        self.email_subject = template.email_subject
        self.email_message = template.email_message
        if template.validity_days:
            self.expiry_date = fields.Date.add(fields.Date.context_today(self), days=template.validity_days)
        self._signr_fill_signers()

    @api.onchange('res_reference')
    def _onchange_res_reference(self):
        if self.res_reference:
            self.res_model = self.res_reference._name
            self.res_id = self.res_reference.id
            self._signr_fill_signers()

    def _signr_fill_signers(self):
        """Signers from the template's signer list, for the request's record."""
        if self.state != 'draft' or not self.template_id:
            return
        record = self.res_reference if self.res_reference else None
        commands = [fields.Command.clear()]
        for index, role in enumerate(self.template_id.role_ids.sorted(lambda r: (r.sequence, r.id))):
            partner = role._signr_partner(record, self.user_id or self.env.user)
            commands.append(fields.Command.create({
                'sequence': (index + 1) * 10 if self.sign_in_order else 10,
                'role': role.name,
                'partner_id': partner.id or False,
            }))
        self.signer_ids = commands

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('signr.request') or '/'
            template = self.env['signr.template'].browse(vals.get('template_id'))
            if not vals.get('res_model') and template:
                vals['res_model'] = template.model_name
            # the Organisation units of the record the request is raised from
            if vals.get('res_model') in self.env and vals.get('res_id'):
                source = self.env[vals['res_model']].sudo().browse(vals['res_id']).exists()
                for name in ORG_FIELDS:
                    if name in self._fields and name not in vals and name in source._fields and source[name]:
                        vals[name] = source[name].id
                if 'company_id' not in vals and 'company_id' in source._fields and source.company_id:
                    vals['company_id'] = source.company_id.id
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def _signr_check_can_change(self):
        """Users who can edit the request, or who created it (Create Only), may send it."""
        try:
            self.check_access('write')
        except AccessError:
            if any(request.create_uid != self.env.user for request in self):
                raise
            self.check_access('read')

    def action_preview(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/signr/request/{self.id}/preview',
            'target': 'new',
        }

    def _signr_prepare_send(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(self.env._('%s has already been sent.', self.display_name))
        self.template_id._signr_check_ready()
        record = self._signr_record()
        if not record:
            raise UserError(self.env._('Pick the record %s is for.', self.display_name))
        # the sender must be able to read the record the document is made from
        self.env[self.res_model].browse(self.res_id).check_access('read')
        if not self.signer_ids:
            raise UserError(self.env._('Add at least one signer to %s.', self.display_name))
        missing = self.signer_ids.filtered(lambda s: not s.partner_id)
        if missing:
            raise UserError(self.env._('Pick who signs as: %s', ', '.join(missing.mapped(lambda s: s.role or '?'))))
        no_email = self.signer_ids.filtered(lambda s: not s.partner_id.email)
        if no_email:
            raise UserError(self.env._('These signers have no email address: %s',
                                       ', '.join(no_email.partner_id.mapped('display_name'))))
        return record

    def action_send(self):
        quick = self.env.context.get('signr_quick')
        # the defaults the dialog was opened with must not reach the emails and notes
        self = self.with_context(clean_context(self.env.context))
        self._signr_check_can_change()
        records = {request.id: request._signr_prepare_send() for request in self}
        for request in self.sudo():
            record = records[request.id]
            docx, pdf = request.template_id._signr_merge(record, request=request)
            if not request.sign_in_order:
                request.signer_ids.write({'sequence': 10})
            request.signer_ids._reset_signature()
            request.write({
                'state': 'sent',
                'sent_date': fields.Datetime.now(),
                'signed_date': False,
                'signed_pdf': False,
                'document_docx': base64.b64encode(docx),
                'document_pdf': base64.b64encode(pdf),
                'document_hash': hashlib.sha256(pdf).hexdigest(),
            })
            request._signr_send_next()
            request._signr_post_on_record(Markup(self.env._(
                'Sent for signature: %(link)s, to %(signers)s.')) % {
                    'link': request._signr_link(), 'signers': request.recipient_names})
        if quick:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'success',
                    'message': self.env._('Sent for signature.'),
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }
        return True

    def _signr_send_next(self):
        """Email the signers whose turn it is: everyone with the lowest order still to sign."""
        self.ensure_one()
        pending = self.signer_ids.filtered(lambda s: s.state in ('waiting', 'sent'))
        if not pending:
            return
        turn = min(pending.mapped('sequence'))
        pending.filtered(lambda s: s.sequence == turn and s.state == 'waiting')._send_request()

    def action_send_reminder(self):
        self = self.with_context(clean_context(self.env.context))
        self._signr_check_can_change()
        for request in self.sudo():
            if request.state != 'sent':
                continue
            waiting = request.signer_ids.filtered(lambda s: s.state == 'sent')
            waiting._send_request(reminder=True)
        return True

    def action_cancel(self):
        self._signr_check_can_change()
        for request in self.sudo():
            if request.state in ('signed', 'cancelled'):
                continue
            request.signer_ids.filtered(lambda s: s.state in ('draft', 'waiting', 'sent')).write(
                {'state': 'cancelled'})
            request.state = 'cancelled'
        return True

    def action_reset_to_draft(self):
        self._signr_check_can_change()
        for request in self.sudo():
            if request.state not in ('cancelled', 'declined', 'expired'):
                raise UserError(self.env._('Only cancelled, declined or expired requests can be reset.'))
            request.signer_ids._reset_signature(state='draft')
            request.write({'state': 'draft', 'sent_date': False, 'signed_date': False,
                           'document_docx': False, 'document_pdf': False, 'document_hash': False,
                           'signed_pdf': False})
        return True

    def action_open_record(self):
        self.ensure_one()
        record = self._signr_record()
        if not record:
            raise UserError(self.env._('The record this request was raised from no longer exists.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------
    def _on_signer_signed(self, signer):
        self.ensure_one()
        self = self.with_context(clean_context(self.env.context))
        self.message_post(body=self.env._('Signed by %(name)s (%(signer)s).', name=signer.signed_by,
                                          signer=signer.partner_id.display_name))
        if all(s.state == 'signed' for s in self.signer_ids):
            self._on_fully_signed()
        else:
            self._signr_send_next()

    def _on_signer_declined(self, signer):
        self.ensure_one()
        self = self.with_context(clean_context(self.env.context))
        self.state = 'declined'
        self.signer_ids.filtered(lambda s: s.state in ('waiting', 'sent')).state = 'cancelled'
        reason = signer.decline_reason or self.env._('no reason given')
        self.message_post(
            body=self.env._('%(signer)s declined to sign: %(reason)s', signer=signer.partner_id.display_name,
                            reason=reason),
            partner_ids=self.user_id.partner_id.ids)
        self.activity_schedule('mail.mail_activity_data_todo', user_id=self.user_id.id,
                               summary=self.env._('Declined by %s', signer.partner_id.display_name),
                               note=reason)
        self._signr_post_on_record(Markup(self.env._('%(link)s was declined by %(signer)s.')) % {
            'link': self._signr_link(), 'signer': signer.partner_id.display_name})

    def _signr_signed_pdf(self):
        """The document with the signatures filled in, followed by the signing certificate."""
        self.ensure_one()
        record = self._signr_record()
        if record:
            _docx, document = self.template_id._signr_merge(record, request=self, with_signatures=True)
        else:
            document = base64.b64decode(self.with_context(bin_size=False).document_pdf or b'')
        certificate, _ftype = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'signr.action_report_signr_certificate', self.ids)
        return merge_pdf([document, certificate]) if document else certificate

    def _on_fully_signed(self):
        """Store the signed PDF, send it to everyone, and file it on the source record."""
        self.ensure_one()
        self.write({'state': 'signed', 'signed_date': fields.Datetime.now()})
        # flush so the PDF shows the signatures just written
        self.env.flush_all()
        attachment = self.env['ir.attachment']
        try:
            with self.env.cr.savepoint():
                pdf = self._signr_signed_pdf()
        except Exception as error:  # noqa: BLE001 - never lose the signatures over the PDF
            _logger.exception("Sign'r: could not create the signed PDF of %s", self.name)
            self.message_post(body=self.env._('Could not create the signed PDF: %s', error),
                              partner_ids=self.user_id.partner_id.ids)
        else:
            self.signed_pdf = base64.b64encode(pdf)
            attachment = self.env['ir.attachment'].sudo().create({
                'name': self.signed_pdf_filename,
                'raw': pdf,
                'mimetype': 'application/pdf',
                'res_model': self._name,
                'res_id': self.id,
            })
        template = self.env.ref('signr.mail_template_signr_completed', raise_if_not_found=False)
        if template:
            self.message_post_with_source(template, subtype_xmlid='mail.mt_comment',
                                          attachment_ids=attachment.ids)
        if attachment:
            record_attachment = attachment.copy({'res_model': self.res_model, 'res_id': self.res_id}) \
                if self._signr_record() else attachment
            self._signr_post_on_record(
                Markup(self.env._('%(link)s has been signed by everyone.')) % {'link': self._signr_link()},
                attachment_ids=record_attachment.ids)
        else:
            self._signr_post_on_record(
                Markup(self.env._('%(link)s has been signed by everyone.')) % {'link': self._signr_link()})

    def _signr_link(self):
        return Markup('<a href="#" data-oe-model="signr.request" data-oe-id="%s">%s</a>') % (
            self.id, self.display_name)

    def _signr_post_on_record(self, body, attachment_ids=None):
        """A note in the chatter of the record the request was raised from, if it has one."""
        record = self._signr_record()
        if not record or not hasattr(record, 'message_post'):
            return
        try:
            record.message_post(body=body, attachment_ids=attachment_ids or [],
                                subtype_xmlid='mail.mt_note')
        except Exception:  # noqa: BLE001 - the note is a courtesy, never block signing
            _logger.warning("Sign'r: could not post on %s,%s", self.res_model, self.res_id, exc_info=True)

    @api.model
    def _cron_expire(self):
        today = fields.Date.context_today(self)
        expired = self.sudo().search([('state', '=', 'sent'), ('expiry_date', '!=', False),
                                      ('expiry_date', '<', today)])
        for request in expired:
            request.signer_ids.filtered(lambda s: s.state in ('waiting', 'sent')).write({'state': 'cancelled'})
            request.state = 'expired'
            request.message_post(body=self.env._('Expired: not everyone signed before %s.',
                                                 request.expiry_date.strftime('%d/%m/%Y')),
                                 partner_ids=request.user_id.partner_id.ids)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_signed(self):
        if any(request.state == 'signed' for request in self):
            raise UserError(self.env._('A signed request cannot be deleted. Archive or keep it as a record.'))


class SignrRequestSigner(models.Model):
    _name = 'signr.request.signer'
    _description = "Sign'r Signer"
    _order = 'request_id, sequence, id'

    request_id = fields.Many2one('signr.request', string='Sign Request', required=True, ondelete='cascade',
                                 index=True)
    company_id = fields.Many2one(related='request_id.company_id', store=True)
    sequence = fields.Integer('Signing Order', default=10,
                              help='Signers sign in this order; signers with the same number are asked at '
                                   'the same time.')
    partner_id = fields.Many2one('res.partner', string='Signer')
    email = fields.Char(related='partner_id.email')
    role = fields.Char('Signs As', help='E.g. Employee, Manager, Customer.')
    is_internal = fields.Boolean('Internal', compute='_compute_is_internal',
                                 help='The signer is one of your users.')
    state = fields.Selection(SIGNER_STATES, string='Status', default='draft', required=True, copy=False)
    access_token = fields.Char(copy=False, groups='base.group_system')
    sent_on = fields.Datetime('Sent On', readonly=True, copy=False)
    viewed_on = fields.Datetime('First Opened On', readonly=True, copy=False)
    signed_on = fields.Datetime('Signed On', readonly=True, copy=False)
    signed_by = fields.Char('Signed As', readonly=True, copy=False,
                            help='The name the signer typed when signing.')
    signature = fields.Image('Signature', readonly=True, copy=False, attachment=True, max_width=1024,
                             max_height=1024)
    signer_ip = fields.Char('Signed From (IP)', readonly=True, copy=False)
    decline_reason = fields.Text('Decline Reason', readonly=True, copy=False)
    sign_url = fields.Char('Signing Link', compute='_compute_sign_url', groups='base.group_system')

    @api.depends('partner_id')
    def _compute_is_internal(self):
        for signer in self:
            signer.is_internal = bool(signer.partner_id.sudo().user_ids.filtered(lambda u: not u.share))

    def _compute_sign_url(self):
        for signer in self:
            signer.sign_url = signer.sudo()._get_sign_url() if signer.sudo().access_token else False

    def _get_sign_url(self):
        self.ensure_one()
        return f'{self.request_id.get_base_url()}/signr/sign/{self.id}/{self.access_token}'

    def _reset_signature(self, state='waiting'):
        for signer in self.sudo():
            signer.write({
                'state': state,
                'access_token': uuid.uuid4().hex if state == 'waiting' else False,
                'sent_on': False, 'viewed_on': False, 'signed_on': False, 'signed_by': False,
                'signature': False, 'signer_ip': False, 'decline_reason': False,
            })

    def _send_request(self, reminder=False):
        template = self.env.ref('signr.mail_template_signr_request').sudo()
        for signer in self.sudo():
            signer.write({'state': 'sent', 'sent_on': signer.sent_on if reminder else fields.Datetime.now()})
            template.with_context(signr_reminder=reminder).send_mail(
                signer.id, email_layout_xmlid='mail.mail_notification_light')
            signer.request_id.message_post(body=(
                self.env._('Reminder sent to %s.', signer.partner_id.display_name) if reminder
                else self.env._('Signature requested from %s.', signer.partner_id.display_name)))

    def _format_signed_on(self):
        """The signing time in the signer's own time zone, as dd/mm/yyyy HH:MM."""
        self.ensure_one()
        if not self.signed_on:
            return ''
        tz_env = self.with_context(tz=self.partner_id.tz or self.request_id.user_id.tz or 'UTC')
        return fields.Datetime.context_timestamp(tz_env, self.signed_on).strftime('%d/%m/%Y %H:%M')

    @api.ondelete(at_uninstall=False)
    def _unlink_except_signed(self):
        if any(signer.state == 'signed' and signer.request_id.state != 'draft' for signer in self):
            raise UserError(self.env._('A signer who has signed cannot be removed.'))

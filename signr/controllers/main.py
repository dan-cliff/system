# -*- coding: utf-8 -*-
"""Signing pages: each signer opens their own private link.

    GET  /signr/sign/<signer>/<token>            the document and the signature form
    POST /signr/sign/<signer>/<token>/accept     sign (JSON, from portal.signature_form)
    POST /signr/sign/<signer>/<token>/decline    decline, with a reason
    GET  /signr/sign/<signer>/<token>/document   the PDF (signed once everyone has)
    GET  /signr/request/<request>/preview        senders: the document before it is sent
"""
import base64
import binascii

from odoo import fields, http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request
from odoo.tools import consteq


class SignrController(http.Controller):

    def _get_signer(self, signer_id, token):
        signer = request.env['signr.request.signer'].sudo().browse(signer_id).exists()
        if not signer or not signer.access_token or not token or not consteq(signer.access_token, token):
            return None
        return signer

    def _can_sign(self, signer):
        sign_request = signer.request_id
        if sign_request.state != 'sent' or signer.state != 'sent':
            return False
        if sign_request.expiry_date and sign_request.expiry_date < fields.Date.context_today(sign_request):
            return False
        # the signer's turn: no one with a lower signing order still to sign
        return not sign_request.signer_ids.filtered(
            lambda s: s.sequence < signer.sequence and s.state in ('waiting', 'sent'))

    def _pdf_response(self, pdf, filename, download=False):
        disposition = http.content_disposition(filename)
        if not download:
            disposition = disposition.replace('attachment', 'inline', 1)
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', disposition),
            ('X-Content-Type-Options', 'nosniff'),
            # shown in the signing page's frame
            ('X-Frame-Options', 'SAMEORIGIN'),
        ])

    @http.route('/signr/sign/<int:signer_id>/<string:token>', type='http', auth='public', website=True,
                sitemap=False)
    def sign_page(self, signer_id, token, message=None, **kwargs):
        signer = self._get_signer(signer_id, token)
        if not signer:
            return request.render('signr.sign_invalid', status=404)
        if not signer.viewed_on and signer.state == 'sent':
            signer.viewed_on = fields.Datetime.now()
            signer.request_id.message_post(
                body=request.env._('Opened by %s.', signer.partner_id.display_name))
        sign_request = signer.request_id
        return request.render('signr.sign_page', {
            'signer': signer,
            'sign_request': sign_request,
            'token': token,
            'can_sign': self._can_sign(signer),
            'expired': sign_request.state == 'expired' or (
                sign_request.expiry_date and sign_request.expiry_date < fields.Date.context_today(sign_request)),
            'message': message,
            'company': sign_request.company_id,
        })

    @http.route('/signr/sign/<int:signer_id>/<string:token>/accept', type='jsonrpc', auth='public',
                website=True)
    def sign_accept(self, signer_id, token, name=None, signature=None, **kwargs):
        signer = self._get_signer(signer_id, token)
        if not signer:
            return {'error': request.env._('This signing link is not valid any more.')}
        if not self._can_sign(signer):
            return {'error': request.env._('This document is not waiting for your signature.')}
        if not name or not name.strip():
            return {'error': request.env._('Type your name to sign.')}
        if not signature:
            return {'error': request.env._('Your signature is missing.')}
        try:
            base64.b64decode(signature, validate=True)
            signer.write({
                'state': 'signed',
                'signed_on': fields.Datetime.now(),
                'signed_by': name.strip(),
                'signature': signature,
                'signer_ip': request.httprequest.remote_addr,
            })
            request.env.cr.flush()
        except (TypeError, ValueError, binascii.Error, UserError):
            return {'error': request.env._('Invalid signature data.')}
        signer.request_id._on_signer_signed(signer)
        return {
            'force_refresh': True,
            'redirect_url': f'/signr/sign/{signer.id}/{token}?message=signed',
        }

    @http.route('/signr/sign/<int:signer_id>/<string:token>/decline', type='http', auth='public',
                methods=['POST'], website=True)
    def sign_decline(self, signer_id, token, decline_reason=None, **kwargs):
        signer = self._get_signer(signer_id, token)
        if not signer:
            return request.render('signr.sign_invalid', status=404)
        if self._can_sign(signer):
            signer.write({'state': 'declined', 'decline_reason': (decline_reason or '').strip() or False})
            signer.request_id._on_signer_declined(signer)
        return request.redirect(f'/signr/sign/{signer.id}/{token}?message=declined')

    @http.route('/signr/sign/<int:signer_id>/<string:token>/document', type='http', auth='public',
                website=True, sitemap=False)
    def sign_document(self, signer_id, token, download=None, **kwargs):
        signer = self._get_signer(signer_id, token)
        if not signer:
            raise request.not_found()
        sign_request = signer.request_id.with_context(bin_size=False)
        if sign_request.signed_pdf:
            return self._pdf_response(base64.b64decode(sign_request.signed_pdf),
                                      sign_request.signed_pdf_filename, download)
        if not sign_request.document_pdf:
            raise request.not_found()
        return self._pdf_response(base64.b64decode(sign_request.document_pdf),
                                  sign_request.document_pdf_filename, download)

    @http.route('/signr/request/<int:request_id>/preview', type='http', auth='user', sitemap=False)
    def preview(self, request_id, **kwargs):
        sign_request = request.env['signr.request'].browse(request_id)
        try:
            sign_request.check_access('read')
            sign_request = sign_request.exists()
            if not sign_request:
                raise MissingError(request.env._('This sign request no longer exists.'))
            record = sign_request._signr_record()
            if not record:
                raise UserError(request.env._('Pick the record this request is for first.'))
            request.env[sign_request.res_model].browse(sign_request.res_id).check_access('read')
            sign_request.template_id._signr_check_ready()
            _docx, pdf = sign_request.template_id._signr_merge(record, request=sign_request)
        except (AccessError, MissingError, UserError) as error:
            return request.make_response(str(error), headers=[('Content-Type', 'text/plain; charset=utf-8')],
                                         status=400)
        return self._pdf_response(pdf, sign_request.document_pdf_filename)

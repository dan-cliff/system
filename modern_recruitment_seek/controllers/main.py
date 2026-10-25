# -*- coding: utf-8 -*-
import hashlib
import hmac
import json
import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class TalentSeekWebhook(http.Controller):

    @http.route('/talent/seek/webhook/<int:company_id>', type='http', auth='public',
                methods=['POST'], csrf=False, save_session=False)
    def seek_webhook(self, company_id, **kwargs):
        """New SEEK applications (CandidateApplicationCreated events), signed
        by SEEK with the company's webhook secret (HMAC-SHA512 of the body)."""
        company = request.env['res.company'].sudo().browse(company_id).exists()
        body = request.httprequest.get_data()
        signature = request.httprequest.headers.get('Seek-Signature', '')
        secret = company.seek_webhook_secret if company else ''
        expected = hmac.new((secret or '').encode(), body, hashlib.sha512).hexdigest()
        if not secret or not hmac.compare_digest(expected, signature.lower()):
            return request.make_response('Invalid signature', status=401)
        try:
            events = json.loads(body or b'{}').get('events') or []
        except ValueError:
            return request.make_response('Invalid body', status=400)
        Applicants = request.env['hr.applicant'].sudo().with_company(company)
        for event in events:
            if event.get('type') != 'CandidateApplicationCreated' or not event.get('candidateApplicationProfileId'):
                continue
            try:
                with request.env.cr.savepoint():
                    Applicants._seek_create_from_profile(event['candidateApplicationProfileId'], company)
            except UserError as error:
                # SEEK retries a failed delivery, so report it rather than drop it.
                _logger.warning('SEEK application %s not imported: %s',
                                event['candidateApplicationProfileId'], error)
                return request.make_response('Retry later', status=503)
        return request.make_response('OK', status=200)

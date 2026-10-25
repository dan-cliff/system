import binascii

from odoo import fields, http
from odoo.http import request
from odoo.tools import consteq, email_normalize


class ModernCrmController(http.Controller):

    # ------------------------------------------------------------------
    # Contract signing: each signer opens their own private link.
    # ------------------------------------------------------------------
    def _get_signer(self, signer_id, token):
        signer = request.env['modern.crm.contract.signer'].sudo().browse(signer_id).exists()
        if not signer or not signer.access_token or not token or not consteq(signer.access_token, token):
            return None
        return signer

    @http.route('/crm/contract/sign/<int:signer_id>/<string:token>', type='http', auth='public', website=True)
    def contract_sign_page(self, signer_id, token, message=None, **kwargs):
        signer = self._get_signer(signer_id, token)
        if not signer:
            return request.render('modern_crm.contract_sign_invalid', status=404)
        contract = signer.contract_id
        # the signer's turn: no one with a lower signing order still to sign
        earlier = contract.signer_ids.filtered(
            lambda s: s.sequence < signer.sequence and s.state in ('waiting', 'sent'))
        return request.render('modern_crm.contract_sign_page', {
            'signer': signer,
            'contract': contract,
            'token': token,
            'can_sign': contract.state == 'out_for_signature' and signer.state == 'sent' and not earlier,
            'message': message,
            'company': contract.company_id,
        })

    @http.route('/crm/contract/sign/<int:signer_id>/<string:token>/accept', type='jsonrpc', auth='public',
                website=True)
    def contract_sign_accept(self, signer_id, token, name=None, signature=None, **kwargs):
        signer = self._get_signer(signer_id, token)
        if not signer:
            return {'error': request.env._('This signing link is not valid any more.')}
        contract = signer.contract_id
        if contract.state != 'out_for_signature' or signer.state != 'sent':
            return {'error': request.env._('This contract is not waiting for your signature.')}
        if not name or not name.strip():
            return {'error': request.env._('Type your name to sign.')}
        if not signature:
            return {'error': request.env._('Your signature is missing.')}
        try:
            signer.write({
                'state': 'signed',
                'signed_on': fields.Datetime.now(),
                'signed_by': name.strip(),
                'signature': signature,
                'signer_ip': request.httprequest.remote_addr,
            })
            request.env.cr.flush()
        except (TypeError, ValueError, binascii.Error):
            return {'error': request.env._('Invalid signature data.')}
        contract._on_signer_signed(signer)
        return {
            'force_refresh': True,
            'redirect_url': f'/crm/contract/sign/{signer.id}/{token}?message=signed',
        }

    @http.route('/crm/contract/sign/<int:signer_id>/<string:token>/decline', type='http', auth='public',
                methods=['POST'], website=True)
    def contract_sign_decline(self, signer_id, token, decline_reason=None, **kwargs):
        signer = self._get_signer(signer_id, token)
        if not signer:
            return request.render('modern_crm.contract_sign_invalid', status=404)
        if signer.contract_id.state == 'out_for_signature' and signer.state == 'sent':
            signer.write({'state': 'declined', 'decline_reason': (decline_reason or '').strip() or False})
            signer.contract_id._on_signer_declined(signer)
        return request.redirect(f'/crm/contract/sign/{signer.id}/{token}?message=declined')

    @http.route('/crm/contract/sign/<int:signer_id>/<string:token>/pdf', type='http', auth='public',
                website=True)
    def contract_sign_pdf(self, signer_id, token, **kwargs):
        signer = self._get_signer(signer_id, token)
        if not signer:
            raise request.not_found()
        contract = signer.contract_id
        if contract.signed_document_id:
            pdf = contract.signed_document_id.raw
        else:
            pdf = contract._render_signed_pdf()
        filename = f'{contract.name}.pdf'.replace('/', '-')
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', http.content_disposition(filename)),
        ])

    # ------------------------------------------------------------------
    # Web-to-Lead form
    # ------------------------------------------------------------------
    WEB_LEAD_FIELDS = ('first_name', 'last_name', 'company_name', 'job_title', 'email', 'phone', 'city')

    @http.route('/crm/web-to-lead', type='http', auth='public', methods=['GET', 'POST'], website=True,
                sitemap=False)
    def web_to_lead(self, **post):
        company = request.env.company.sudo()
        if not company.modern_crm_web_to_lead:
            raise request.not_found()
        values = {'post': post, 'errors': {}, 'company': company}
        if request.httprequest.method == 'POST':
            # bots fill in every field, including the hidden one
            if post.get('website_url'):
                return request.render('modern_crm.web_to_lead_thanks', values)
            if not post.get('last_name', '').strip():
                values['errors']['last_name'] = True
            if not email_normalize(post.get('email', '')):
                values['errors']['email'] = True
            if not values['errors']:
                lead_values = {f: post[f].strip() for f in self.WEB_LEAD_FIELDS if post.get(f, '').strip()}
                lead_values.update({
                    'description': post.get('description', '').strip() or False,
                    'company_id': company.id,
                    'user_id': company.modern_crm_web_lead_user_id.id,
                    'team_id': company.modern_crm_web_lead_team_id.id,
                    'lead_source_id': (request.env.ref('modern_crm.lead_source_web', raise_if_not_found=False)
                                       or request.env['modern.crm.lead.source']).id,
                })
                request.env['modern.crm.lead'].sudo().create(lead_values)
                return request.render('modern_crm.web_to_lead_thanks', values)
        return request.render('modern_crm.web_to_lead_form', values)

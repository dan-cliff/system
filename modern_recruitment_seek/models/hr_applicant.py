# -*- coding: utf-8 -*-
import base64
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

CANDIDATE_QUERY = """
query TalentSeekCandidate($id: String!) {
  candidateProfile(id: $id) {
    profileId { value }
    candidate {
      person {
        name { formattedName given family }
        communication {
          email { address }
          phone { formattedNumber }
        }
      }
    }
    associatedPositionProfile { profileId { value } }
    attachments { descriptions seekRoleCode url }
  }
}
"""


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    seek_candidate_profile_id = fields.Char(string='SEEK Application ID', copy=False, readonly=True, index=True)

    @api.model
    def _seek_create_from_profile(self, profile_id, company):
        """Create the applicant for a SEEK application (once per application)."""
        existing = self.with_context(active_test=False).search(
            [('seek_candidate_profile_id', '=', profile_id)], limit=1)
        if existing:
            return existing
        api_model = self.env['talent.seek.api']
        data = api_model._seek_query(CANDIDATE_QUERY, {'id': profile_id}, company).get('candidateProfile')
        if not data:
            _logger.info('SEEK application %s not found', profile_id)
            return self.browse()
        person = (data.get('candidate') or {}).get('person') or {}
        name = person.get('name') or {}
        communication = person.get('communication') or {}
        emails = [e.get('address') for e in communication.get('email') or [] if e.get('address')]
        phones = [p.get('formattedNumber') for p in communication.get('phone') or [] if p.get('formattedNumber')]
        ad_id = ((data.get('associatedPositionProfile') or {}).get('profileId') or {}).get('value')
        job = ad_id and self.env['hr.job'].with_context(active_test=False).search(
            [('seek_profile_id', '=', ad_id)], limit=1)
        source = self.env.ref('modern_recruitment_seek.utm_source_seek')
        medium = self.env['utm.medium'].search([('name', '=', 'Job Board')], limit=1) \
            or self.env['utm.medium'].create({'name': 'Job Board'})
        applicant = self.with_company(job.company_id or company).create({
            'partner_name': name.get('formattedName') or ' '.join(
                filter(None, (name.get('given'), name.get('family')))) or self.env._('SEEK applicant'),
            'email_from': emails[0] if emails else False,
            'partner_phone': phones[0] if phones else False,
            'job_id': job.id if job else False,
            'company_id': (job.company_id or company).id,
            'source_id': source.id,
            'medium_id': medium.id,
            'seek_candidate_profile_id': profile_id,
        })
        for attachment in data.get('attachments') or []:
            applicant._seek_attach(attachment, company)
        applicant.message_post(body=self.env._('Applied on SEEK.'))
        return applicant

    def _seek_attach(self, attachment, company):
        self.ensure_one()
        if not attachment.get('url'):
            return
        try:
            content, mimetype = self.env['talent.seek.api']._seek_download(attachment['url'], company)
        except Exception as error:  # noqa: BLE001 - a missing file must not lose the application
            _logger.info('SEEK attachment download failed: %s', error)
            return
        role = attachment.get('seekRoleCode') or 'Attachment'
        label = {'Resume': self.env._('Résumé'), 'CoverLetter': self.env._('Cover Letter')}.get(role, role)
        extension = {'application/pdf': '.pdf', 'application/msword': '.doc',
                     'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
                     'text/plain': '.txt', 'application/rtf': '.rtf'}.get(mimetype, '')
        self.env['ir.attachment'].create({
            'name': '%s - %s%s' % (label, self.partner_name, extension),
            'datas': base64.b64encode(content),
            'mimetype': mimetype,
            'res_model': self._name,
            'res_id': self.id,
        })

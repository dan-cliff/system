# -*- coding: utf-8 -*-
import hmac
from datetime import timezone
from email.utils import format_datetime

from lxml import etree

from odoo import fields, http
from odoo.http import request


def _cdata(parent, tag, value):
    etree.SubElement(parent, tag).text = etree.CDATA(str(value or '').replace(']]>', ']] >'))


class TalentLinkedinFeed(http.Controller):

    @http.route('/talent/linkedin/<int:company_id>/<string:token>/jobs.xml',
                type='http', auth='public', methods=['GET'], csrf=False, save_session=False)
    def linkedin_feed(self, company_id, token, **kwargs):
        company = request.env['res.company'].sudo().browse(company_id).exists()
        if not company or not company.linkedin_feed_token or \
                not hmac.compare_digest(company.linkedin_feed_token, token):
            raise request.not_found()
        jobs = request.env['hr.job'].sudo().with_company(company)._linkedin_feed_jobs(company)
        source = etree.Element('source')
        # RFC 822, as LinkedIn's feed format requires (machine-read, not shown to users).
        etree.SubElement(source, 'lastBuildDate').text = format_datetime(
            fields.Datetime.now().replace(tzinfo=timezone.utc), usegmt=True)
        etree.SubElement(source, 'publisherUrl').text = company.get_base_url()
        etree.SubElement(source, 'publisher').text = company.name
        etree.SubElement(source, 'expectedJobCount').text = str(len(jobs))
        for job in jobs:
            node = etree.SubElement(source, 'job')
            for tag, value in job._linkedin_feed_vals().items():
                if value:
                    _cdata(node, tag, value)
        body = etree.tostring(source, xml_declaration=True, encoding='UTF-8', pretty_print=True)
        return request.make_response(body, headers=[('Content-Type', 'application/xml; charset=utf-8')])

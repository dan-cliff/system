# -*- coding: utf-8 -*-
import hmac

from lxml import etree

from odoo import http
from odoo.http import request


class TalentJoraFeed(http.Controller):

    @http.route('/talent/jora/<int:company_id>/<string:token>/jobs.xml',
                type='http', auth='public', methods=['GET'], csrf=False, save_session=False)
    def jora_feed(self, company_id, token, **kwargs):
        company = request.env['res.company'].sudo().browse(company_id).exists()
        if not company or not company.jora_feed_token or not hmac.compare_digest(company.jora_feed_token, token):
            raise request.not_found()
        jobs = request.env['hr.job'].sudo().with_company(company)._jora_feed_jobs(company)
        source = etree.Element('source')
        etree.SubElement(source, 'publisher').text = company.name
        etree.SubElement(source, 'publisherurl').text = company.get_base_url()
        for job in jobs:
            node = etree.SubElement(source, 'job')
            for tag, value in job._jora_feed_vals().items():
                if value:
                    etree.SubElement(node, tag).text = etree.CDATA(str(value).replace(']]>', ']] >'))
        body = etree.tostring(source, xml_declaration=True, encoding='UTF-8', pretty_print=True)
        return request.make_response(body, headers=[('Content-Type', 'application/xml; charset=utf-8')])

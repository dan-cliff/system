# -*- coding: utf-8 -*-
import base64
import logging
import os

from odoo import http
from odoo.http import request, content_disposition

_logger = logging.getLogger(__name__)


class ReportBuilderController(http.Controller):

    @http.route('/report_builder/download/<int:report_id>',
                type='http', auth='user', methods=['GET'])
    def download_report(self, report_id, **kwargs):
        """Stream the generated report file to the browser."""
        report = request.env['report.builder'].browse(report_id)
        if not report.exists():
            return request.not_found()

        try:
            fname, data, mime = report.generate_report_bytes()
        except Exception as e:
            _logger.exception('Report Builder: error generating report %d', report_id)
            return request.make_response(
                'Error generating report: %s' % str(e),
                headers=[('Content-Type', 'text/plain')],
                status=500,
            )

        headers = [
            ('Content-Type', mime),
            ('Content-Disposition', content_disposition(fname)),
            ('Content-Length', len(data)),
        ]
        return request.make_response(data, headers=headers)

    @http.route('/report_builder/user-guide',
                type='http', auth='user', methods=['GET'])
    def download_user_guide(self, **kwargs):
        """Serve the Report Builder user guide HTML as a download."""
        guide_path = os.path.join(
            os.path.dirname(__file__), '..', 'static', 'report_builder_user_guide.html'
        )
        guide_path = os.path.abspath(guide_path)
        try:
            with open(guide_path, 'rb') as f:
                data = f.read()
        except FileNotFoundError:
            return request.not_found()

        headers = [
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Content-Disposition', content_disposition('Report_Builder_User_Guide.html')),
            ('Content-Length', len(data)),
        ]
        return request.make_response(data, headers=headers)

    @http.route('/report_builder/fields/<string:model_name>',
                type='jsonrpc', auth='user', methods=['POST'])
    def get_model_fields(self, model_name, **kwargs):
        """Return list of fields for a given model (for field selector)."""
        try:
            model = request.env[model_name]
        except KeyError:
            return {'error': 'Model not found'}

        fields_info = []
        for fname, field in sorted(model._fields.items()):
            if fname.startswith('_'):
                continue
            fields_info.append({
                'name': fname,
                'string': field.string or fname,
                'ttype': field.type,
                'comodel': getattr(field, 'comodel_name', None),
            })
        return {'fields': fields_info}

# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import content_disposition, request


class ChecklistsController(http.Controller):

    @http.route('/checklists/templates/export', type='http', auth='user')
    def export_templates(self, ids):
        Templates = request.env['checklist.template'].with_context(active_test=False)
        templates = Templates.browse([int(i) for i in ids.split(',') if i.isdigit()]).exists()
        if not templates:
            raise request.not_found()
        templates.check_access('read')
        if len(templates) == 1:
            return request.make_response(
                templates._export_json(),
                headers=[
                    ('Content-Type', 'application/json; charset=utf-8'),
                    ('Content-Disposition', content_disposition(templates._export_filename())),
                ],
            )
        return request.make_response(
            templates._export_zip(),
            headers=[
                ('Content-Type', 'application/zip'),
                ('Content-Disposition', content_disposition('Checklist Templates.zip')),
            ],
        )

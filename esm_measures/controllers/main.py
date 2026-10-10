# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import content_disposition, request


class EsmMeasuresController(http.Controller):

    @http.route('/esm_measures/templates/export', type='http', auth='user')
    def export_templates(self, model, ids):
        Templates = request.env.get(model)
        if Templates is None or not isinstance(Templates, request.env.registry['esm.template.mixin']):
            raise request.not_found()
        templates = Templates.browse([int(i) for i in ids.split(',') if i]).exists()
        if not templates:
            raise request.not_found()
        templates.check_access('read')
        name = templates.name if len(templates) == 1 else Templates._description + 's'
        return request.make_response(
            templates._export_json(),
            headers=[
                ('Content-Type', 'application/json; charset=utf-8'),
                ('Content-Disposition', content_disposition(f'{name}.json')),
            ],
        )

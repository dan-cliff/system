# -*- coding: utf-8 -*-
from odoo import http
from odoo.exceptions import UserError, ValidationError
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

    # ── Public Link (no sign-in) ──────────────────────────────────────────

    @http.route('/checklists/public/<string:token>', type='http', auth='public',
                methods=['GET', 'POST'], sitemap=False)
    def public_checklist(self, token, **_post):
        template = request.env['checklist.template'].sudo()._public_template(token)
        if not template:
            raise request.not_found()
        Checklist = request.env['checklist.checklist'].sudo()
        error = False
        if request.httprequest.method == 'POST':
            try:
                with request.env.cr.savepoint():
                    checklist = Checklist._public_submit(
                        template, request.httprequest.form, request.httprequest.files)
            except (UserError, ValidationError) as exc:
                error = exc.args[0] if exc.args else str(exc)
            else:
                return request.render('checklists.public_checklist_done', {
                    'template': template, 'checklist': checklist,
                    'title': template.name,
                })
        values = Checklist._public_form_values(template)
        values.update(error=error, form=request.httprequest.form if error else {}, title=template.name)
        return request.render('checklists.public_checklist_page', values)

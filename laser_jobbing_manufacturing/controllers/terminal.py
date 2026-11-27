# -*- coding: utf-8 -*-
"""Laser files for the Work Centre app, served through the work centre's own link
(the app has no Odoo user: its link is its key)."""
from odoo import http
from odoo.http import request

from odoo.addons.advanced_manufacturing.controllers.terminal import PREFIX, _get_workcenter
from odoo.addons.laser_jobbing.controllers.main import image_response
from odoo.addons.laser_jobbing.models.laser_template import binary_bytes
from odoo.addons.laser_jobbing.tools.formats import MIMETYPES


class LaserTerminalController(http.Controller):

    @http.route(PREFIX + '/<string:token>/laser/<int:job_id>/<string:kind>', type='http', auth='public',
                methods=['GET'], csrf=False, save_session=False)
    def laser_terminal_file(self, token, job_id, kind, **kwargs):
        workcenter = _get_workcenter(token)
        job = request.env['laser.job'].sudo().browse(job_id).exists()
        if (
            not workcenter or not job or not job.output_file or kind not in ('file', 'preview')
            or workcenter not in job.production_id.workorder_ids.workcenter_id
        ):
            return request.not_found()
        data = binary_bytes(job, 'output_file')
        if kind == 'preview':
            return image_response(data, job.output_format)
        return request.make_response(data, headers=[
            ('Content-Type', MIMETYPES.get(job.output_format, 'application/octet-stream')),
            ('Content-Disposition', http.content_disposition(job.output_filename)),
            ('Cache-Control', 'no-store'),
            ('X-Content-Type-Options', 'nosniff'),
        ])

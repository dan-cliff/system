# -*- coding: utf-8 -*-
"""Files the visual editors and previews show in the browser.

SVGs are always sanitised and served with a Content-Security-Policy that
blocks scripts, and pictures browsers can't show (tif, tiff, heic) are
converted to PNG for the preview. The files the laser runs are downloaded
from the job itself.
"""
from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.tools import consteq

from ..models.laser_template import binary_bytes
from ..tools import formats, raster_tools, svg_tools
from ..tools.formats import extension

SVG_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:"


def image_response(data, ext):
    """Serve picture or SVG data for display."""
    if not data:
        return request.not_found()
    try:
        if ext == 'svg':
            body, mimetype = svg_tools.sanitized_svg(data), 'image/svg+xml'
        elif ext in formats.BROWSER_EXTENSIONS:
            body, mimetype = data, formats.MIMETYPES[ext]
        else:
            if ext == 'heic' and not raster_tools.HEIF_SUPPORTED:
                return request.not_found()
            body, mimetype = raster_tools.to_png(data), 'image/png'
    except (svg_tools.SvgError, raster_tools.RasterError):
        return request.not_found()
    headers = [
        ('Content-Type', mimetype),
        ('Cache-Control', 'private, max-age=604800'),
        ('X-Content-Type-Options', 'nosniff'),
    ]
    if mimetype == 'image/svg+xml':
        headers.append(('Content-Security-Policy', SVG_CSP))
    return request.make_response(body, headers=headers)


def readable(record):
    """The record when the current user may read it, else None."""
    try:
        record.check_access('read')
        return record
    except (AccessError, MissingError):
        return None


def job_with_token(job_id, access_token):
    """A job (sudo) the visitor may see: by its access token, or by their access rights."""
    job = request.env['laser.job'].sudo().browse(int(job_id)).exists()
    if not job:
        return None
    if access_token and consteq(job.access_token or '', str(access_token)):
        return job
    if request.env.user._is_internal() and readable(request.env['laser.job'].browse(job.id)):
        return job
    return None


def template_visible(template):
    """Whether the visitor may see a template's design (employees, or a template sold online)."""
    if not template:
        return False
    if request.env.user._is_internal() and readable(request.env['laser.template'].browse(template.id)):
        return True
    return template._laser_public_access()


class LaserJobbingController(http.Controller):

    @http.route('/laser_jobbing/template/<int:template_id>/base', type='http', auth='public',
                methods=['GET'], sitemap=False)
    def template_base(self, template_id, **kwargs):
        template = request.env['laser.template'].sudo().browse(template_id).exists()
        if not template_visible(template) or not template.base_file:
            return request.not_found()
        return image_response(binary_bytes(template, 'base_file'), template.base_format)

    @http.route('/laser_jobbing/element/<int:element_id>/image', type='http', auth='public',
                methods=['GET'], sitemap=False)
    def element_image(self, element_id, **kwargs):
        element = request.env['laser.template.element'].sudo().browse(element_id).exists()
        if not element or not template_visible(element.template_id) or not element.default_image:
            return request.not_found()
        return image_response(binary_bytes(element, 'default_image'), extension(element.default_image_filename))

    @http.route('/laser_jobbing/font/<int:font_id>', type='http', auth='public', methods=['GET'],
                sitemap=False)
    def font_file(self, font_id, **kwargs):
        font = request.env['laser.font'].sudo().browse(font_id).exists()
        data = font._font_data() if font and font.active else None
        if not data:
            return request.not_found()
        mimetype = 'font/otf' if extension(font.font_filename) == 'otf' else 'font/ttf'
        return request.make_response(data, headers=[
            ('Content-Type', mimetype),
            ('Cache-Control', 'public, max-age=604800'),
            ('X-Content-Type-Options', 'nosniff'),
        ])

    @http.route('/laser_jobbing/job/<int:job_id>/preview', type='http', auth='public', methods=['GET'],
                sitemap=False)
    def job_preview(self, job_id, access_token=None, **kwargs):
        job = job_with_token(job_id, access_token)
        if not job or not job.output_file:
            return request.not_found()
        return image_response(binary_bytes(job, 'output_file'), job.output_format)

    @http.route('/laser_jobbing/value/<int:value_id>/image', type='http', auth='public', methods=['GET'],
                sitemap=False)
    def value_image(self, value_id, access_token=None, **kwargs):
        value = request.env['laser.job.value'].sudo().browse(value_id).exists()
        if not value or not value.image or not job_with_token(value.job_id.id, access_token):
            return request.not_found()
        return image_response(binary_bytes(value, 'image'), extension(value.image_filename))

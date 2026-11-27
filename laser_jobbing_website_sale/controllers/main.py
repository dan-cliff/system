# -*- coding: utf-8 -*-
import base64

from odoo import _, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.tools import consteq

from odoo.addons.laser_jobbing.models.laser_template import max_upload_bytes
from odoo.addons.laser_jobbing.tools import formats


class LaserPersonaliserController(http.Controller):

    def _laser_product(self, product_template_id):
        product = request.env['product.template'].search(
            request.website.sale_product_domain() + [('id', '=', int(product_template_id or 0))], limit=1,
        )
        if not product or not product.laser_shop_personalised:
            raise UserError(_('This product cannot be personalised.'))
        return product

    def _laser_variant(self, product, variant_id):
        variant = product.product_variant_ids.filtered(lambda v: str(v.id) == str(variant_id or ''))
        return variant or product.product_variant_id

    def _laser_job(self, job_id, access_token):
        job = request.env['laser.job'].sudo().browse(int(job_id or 0)).exists()
        if not job or job.source != 'website' or not access_token or not consteq(
            job.access_token or '', str(access_token)
        ):
            raise UserError(_('This personalisation has expired. Please fill it in again.'))
        return job

    def _laser_values(self, template, job, params, files):
        """Value commands for the customer's elements, checked like the job form."""
        limit = max_upload_bytes(request.env)
        existing = {value.element_id.id: value for value in job.value_ids} if job else {}
        commands = []
        for element in template.element_ids.filtered('customer_editable'):
            value = existing.get(element.id)
            if element.element_type == 'text':
                text = (params.get('text_%s' % element.id) or '').strip('\r\n')
                if element.max_length and len(text) > element.max_length:
                    raise UserError(_('"%(name)s" can have up to %(limit)s characters.',
                                      name=element.name, limit=element.max_length))
                if not element.multiline:
                    text = ' '.join(text.splitlines())
                vals = {'text_value': text or False}
            else:
                upload = files.get('image_%s' % element.id)
                if not upload or not getattr(upload, 'filename', None):
                    if params.get('clear_%s' % element.id):
                        vals = {'image': False, 'image_filename': False}
                    else:
                        continue  # keep what was uploaded before
                else:
                    if formats.extension(upload.filename) not in formats.allowed_extensions(template.operation):
                        raise UserError(_('"%(name)s" must be one of: %(formats)s.', name=element.name,
                                          formats=formats.accept_attribute(template.operation)))
                    data = upload.read(limit + 1)
                    if len(data) > limit:
                        raise UserError(_('"%(name)s" is too large (the limit is %(mb)s MB).',
                                          name=element.name, mb=limit // (1024 * 1024)))
                    if not data:
                        raise UserError(_('"%s" is empty.', element.name))
                    vals = {'image': base64.b64encode(data), 'image_filename': upload.filename}
            if value:
                commands.append((1, value.id, vals))
            else:
                commands.append((0, 0, dict(vals, element_id=element.id)))
        return commands

    @http.route('/shop/laser/design', type='http', auth='public', website=True, methods=['POST'],
                csrf=True, sitemap=False)
    def laser_design(self, product_template_id=None, product_id=None, quantity=1, job_id=None,
                     access_token=None, **kwargs):
        """Save the customer's personalisation as a draft job and make its file."""
        try:
            product = self._laser_product(product_template_id)
            template = product.sudo().laser_template_id
            variant = self._laser_variant(product, product_id)
            website = request.website
            Job = request.env['laser.job'].sudo().with_company(website.company_id).with_context(
                laser_defer_output=True)
            job = self._laser_job(job_id, access_token) if job_id else Job.browse()
            if job and (job.template_id != template or job.state != 'draft' or job.sale_line_ids):
                job = Job.browse()  # changed product, or already ordered: start a new one
            files = request.httprequest.files
            try:
                commands = self._laser_values(template, job, kwargs, files)
                if job:
                    job.with_context(laser_defer_output=True).write({
                        'product_id': variant.id,
                        'quantity': max(float(quantity or 1), 1),
                        'value_ids': commands,
                    })
                else:
                    partner = request.env.user.partner_id if not website.is_public_user() else False
                    job = Job.create({
                        'template_id': template.id,
                        'product_id': variant.id,
                        'quantity': max(float(quantity or 1), 1),
                        'company_id': website.company_id.id,
                        'partner_id': partner.id if partner else False,
                        'source': 'website',
                        'user_id': False,
                        'value_ids': commands,
                    })
                job._check_complete()
                job._generate_output()
            except ValidationError as error:
                raise UserError(str(error.args[0] if error.args else error)) from error
            return request.make_json_response(job._laser_website_values())
        except UserError as error:
            request.env.cr.rollback()
            return request.make_json_response({'error': str(error.args[0] if error.args else error)}, status=400)

    @http.route('/shop/laser/add-to-cart', type='jsonrpc', auth='public', website=True, sitemap=False)
    def laser_add_to_cart(self, job_id, access_token, quantity=1, **kwargs):
        job = self._laser_job(job_id, access_token)
        if job.state != 'draft' or not job.output_file:
            raise UserError(_('This personalisation could not be made. Please check it and try again.'))
        quantity = max(int(float(quantity or 1)), 1)
        order_sudo = request.cart or request.website._create_cart()
        if job.sale_line_ids - order_sudo.order_line:
            raise UserError(_('This personalisation has already been ordered. Please fill it in again.'))
        if not job.partner_id and order_sudo.partner_id != request.website.user_id.partner_id:
            job.partner_id = order_sudo.partner_id
        job.quantity = quantity
        order_sudo._cart_add(product_id=job.product_id.id, quantity=quantity, laser_job_id=job.id)
        return {'redirect': '/shop/cart', 'cart_quantity': order_sudo.cart_quantity}

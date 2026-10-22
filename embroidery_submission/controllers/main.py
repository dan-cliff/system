# -*- coding: utf-8 -*-
import base64

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import consteq
from odoo.tools.misc import formatLang


class EmbroideryQuoteController(http.Controller):

    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────

    def _embroidery_products(self):
        return request.env['product.template'].search(
            request.website.sale_product_domain() + [
                ('embroidery_dynamic_pricing', '=', True),
                ('is_published', '=', True),
            ]
        )

    def _embroidery_get_submission(self, submission_id, access_token):
        submission = request.env['embroidery.submission'].sudo().browse(int(submission_id or 0)).exists()
        if not submission or submission.source != 'website' or not access_token or not consteq(
            submission.access_token or '', str(access_token)
        ):
            raise UserError(_('This quote has expired. Please upload your file again.'))
        return submission

    def _embroidery_display_price(self, submission):
        """Price per piece as the shop shows it (pricelist currency, with or without taxes)."""
        website = request.website
        currency = website.currency_id
        product = submission.product_id.sudo()
        price = submission.currency_id._convert(
            submission.price, currency, website.company_id, submission.create_date.date(),
        )
        product_taxes = product.taxes_id._filter_taxes_by_company(website.company_id)
        taxes = request.fiscal_position.map_tax(product_taxes) if product_taxes else product_taxes
        price = request.env['product.template']._apply_taxes_to_price(
            price, currency, product_taxes, taxes, product, website=website,
        )
        return price, currency

    def _embroidery_quote_values(self, submission, quantity=1):
        price, currency = self._embroidery_display_price(submission)
        quantity = max(int(quantity or 1), 1)
        return {
            'submission_id': submission.id,
            'access_token': submission.access_token,
            'state': submission.state,
            'error': submission.error_message or '',
            'warnings': (submission.warnings or '').splitlines(),
            'filename': submission.filename,
            'stitch_count': submission.stitch_count,
            'stitch_count_formatted': '{:,}'.format(submission.stitch_count),
            'color_count': submission.color_count,
            'color_change_count': submission.color_change_count,
            'size': submission.size_display or '',
            'duration': submission.duration_display or '',
            'stitches_per_minute': submission.stitches_per_minute,
            'colors': [{
                'name': color.name or '',
                'hex': color.color_hex or '',
                'stitches': '{:,}'.format(color.stitch_count),
            } for color in submission.color_ids],
            'preview': (
                'data:image/png;base64,%s' % submission.image_256.decode() if submission.image_256 else ''
            ),
            'price': price,
            'price_formatted': formatLang(request.env, price, currency_obj=currency),
            'total_formatted': formatLang(request.env, price * quantity, currency_obj=currency),
            'tax_included': request.website.show_line_subtotals_tax_selection != 'tax_excluded',
        }

    # ─────────────────────────────────────────────────────────────────────
    # Pages
    # ─────────────────────────────────────────────────────────────────────

    @http.route('/shop/embroidery-quote', type='http', auth='public', website=True, sitemap=True)
    def embroidery_quote_page(self, product_id=None, **kwargs):
        products = self._embroidery_products()
        selected = products.filtered(lambda p: str(p.id) == str(product_id or '')) or products[:1]
        return request.render('embroidery_submission.embroidery_quote_page', {
            'embroidery_products': products,
            'embroidery_product': selected,
        })

    # ─────────────────────────────────────────────────────────────────────
    # Quote API
    # ─────────────────────────────────────────────────────────────────────

    @http.route('/shop/embroidery-quote/upload', type='http', auth='public', website=True,
                methods=['POST'], csrf=True, sitemap=False)
    def embroidery_quote_upload(self, product_id=None, quantity=1, file=None, **kwargs):
        try:
            product_tmpl = self._embroidery_products().filtered(lambda p: str(p.id) == str(product_id or ''))
            if not product_tmpl:
                raise UserError(_('This product cannot be quoted from an embroidery file.'))
            if not file or not getattr(file, 'filename', None):
                raise UserError(_('Choose a .pes embroidery file to upload.'))
            filename = file.filename
            if not filename.lower().endswith('.pes'):
                raise UserError(_('Only Brother .pes embroidery files can be priced.'))
            max_mb = request.env['product.template']._embroidery_max_upload_mb()
            data = file.read(max_mb * 1024 * 1024 + 1)
            if len(data) > max_mb * 1024 * 1024:
                raise UserError(_('The file is too large (the limit is %s MB).', max_mb))
            if not data:
                raise UserError(_('The file is empty.'))

            website = request.website
            partner = request.env.user.partner_id if not website.is_public_user() else False
            submission = request.env['embroidery.submission'].sudo().with_company(website.company_id).create({
                'file': base64.b64encode(data),
                'filename': filename,
                'product_id': product_tmpl.product_variant_id.id,
                'company_id': website.company_id.id,
                'partner_id': partner.id if partner else False,
                'source': 'website',
            })
            return request.make_json_response(self._embroidery_quote_values(submission, quantity))
        except UserError as e:
            return request.make_json_response({'error': str(e)}, status=400)

    @http.route('/shop/embroidery-quote/update', type='jsonrpc', auth='public', website=True, sitemap=False)
    def embroidery_quote_update(self, submission_id, access_token, quantity=1, **kwargs):
        submission = self._embroidery_get_submission(submission_id, access_token)
        return self._embroidery_quote_values(submission, quantity)

    @http.route('/shop/embroidery-quote/add-to-cart', type='jsonrpc', auth='public', website=True, sitemap=False)
    def embroidery_quote_add_to_cart(self, submission_id, access_token, quantity=1, **kwargs):
        submission = self._embroidery_get_submission(submission_id, access_token)
        if submission.state != 'done' or not submission.price:
            raise UserError(_('This file could not be priced, so it cannot be added to the cart.'))
        quantity = max(int(quantity or 1), 1)
        order_sudo = request.cart or request.website._create_cart()
        if submission.sale_line_ids - order_sudo.order_line:
            raise UserError(_('This quote has already been ordered. Please upload the file again.'))
        if not submission.partner_id and order_sudo.partner_id != request.website.user_id.partner_id:
            submission.partner_id = order_sudo.partner_id
        order_sudo._cart_add(
            product_id=submission.product_id.id,
            quantity=quantity,
            embroidery_submission_id=submission.id,
        )
        return {'redirect': '/shop/cart', 'cart_quantity': order_sudo.cart_quantity}

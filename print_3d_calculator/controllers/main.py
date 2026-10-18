import base64
import logging

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import consteq
from odoo.tools.misc import formatLang

from ..tools import print_file_parser

_logger = logging.getLogger(__name__)


class Print3dQuoteController(http.Controller):

    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────

    def _print3d_products(self):
        website = request.website
        return request.env['product.template'].search(
            website.sale_product_domain() + [
                ('print3d_dynamic_pricing', '=', True),
                ('is_published', '=', True),
            ]
        )

    def _print3d_materials(self):
        return request.env['product.template']._print3d_website_materials()

    def _print3d_max_bytes(self):
        return request.env['product.template']._print3d_max_upload_mb() * 1024 * 1024

    def _print3d_get_estimate(self, estimate_id, access_token):
        estimate = request.env['print3d.estimate'].sudo().browse(int(estimate_id or 0)).exists()
        if not estimate or estimate.source != 'website' or not access_token or not consteq(
            estimate.access_token or '', str(access_token)
        ):
            raise UserError(_('This quote has expired. Please upload your file again.'))
        return estimate

    def _print3d_display_price(self, estimate, quantity=1):
        """Price per print as the shop shows it (pricelist currency, with or without taxes)."""
        website = request.website
        currency = website.currency_id
        product = estimate.product_id.sudo()
        price = estimate.currency_id._convert(
            estimate.price, currency, website.company_id, estimate.create_date.date(),
        )
        product_taxes = product.taxes_id._filter_taxes_by_company(website.company_id)
        taxes = request.fiscal_position.map_tax(product_taxes) if product_taxes else product_taxes
        price = request.env['product.template']._apply_taxes_to_price(
            price, currency, product_taxes, taxes, product, website=website,
        )
        return price, currency

    def _print3d_quote_values(self, estimate, quantity=1):
        price, currency = self._print3d_display_price(estimate)
        materials = self._print3d_materials()
        return {
            'estimate_id': estimate.id,
            'access_token': estimate.access_token,
            'state': estimate.state,
            'error': estimate.error_message or '',
            'warnings': (estimate.warnings or '').splitlines(),
            'filename': estimate.filename,
            'file_format': dict(estimate._fields['file_format'].selection).get(estimate.file_format, ''),
            'slicer': estimate.slicer or '',
            'sliced': estimate.sliced,
            'filament_count': estimate.filament_count,
            'total_filament_g': round(estimate.total_filament_g, 1),
            'total_filament_m': round(estimate.total_filament_m, 2),
            'print_time': estimate.print_time_display or '',
            'size': (
                '%.0f × %.0f × %.0f mm' % (estimate.size_x_mm, estimate.size_y_mm, estimate.size_z_mm)
                if estimate.size_x_mm else ''
            ),
            'lines': [{
                'id': line.id,
                'slot': line.slot,
                'colour': line.colour or '',
                'file_material': line.slicer_material or '',
                'material_id': line.material_id.id,
                'weight_g': round(line.weight_g, 1),
                'length_m': round(line.length_m, 2),
            } for line in estimate.line_ids],
            'materials': [{'id': m.id, 'name': m.name} for m in materials],
            'price': price,
            'price_formatted': formatLang(request.env, price, currency_obj=currency),
            'total_formatted': formatLang(request.env, price * max(int(quantity or 1), 1), currency_obj=currency),
            'tax_included': request.website.show_line_subtotals_tax_selection != 'tax_excluded',
        }

    # ─────────────────────────────────────────────────────────────────────
    # Pages
    # ─────────────────────────────────────────────────────────────────────

    @http.route('/shop/3d-print-quote', type='http', auth='public', website=True, sitemap=True)
    def print3d_quote_page(self, product_id=None, **kwargs):
        products = self._print3d_products()
        selected = products.filtered(lambda p: str(p.id) == str(product_id or '')) or products[:1]
        return request.render('print_3d_calculator.print3d_quote_page', {
            'print3d_products': products,
            'print3d_product': selected,
        })

    # ─────────────────────────────────────────────────────────────────────
    # Quote API
    # ─────────────────────────────────────────────────────────────────────

    @http.route('/shop/3d-print-quote/upload', type='http', auth='public', website=True,
                methods=['POST'], csrf=True, sitemap=False)
    def print3d_quote_upload(self, product_id=None, material_id=None, quantity=1, file=None, **kwargs):
        try:
            product_tmpl = self._print3d_products().filtered(lambda p: str(p.id) == str(product_id or ''))
            if not product_tmpl:
                raise UserError(_('This product cannot be quoted from a 3D file.'))
            if not file or not getattr(file, 'filename', None):
                raise UserError(_('Choose a 3D print file to upload.'))
            filename = file.filename
            if not filename.lower().endswith(print_file_parser.SUPPORTED_EXTENSIONS):
                raise UserError(_(
                    'Unsupported file type. Supported types: %s.',
                    ', '.join(print_file_parser.SUPPORTED_EXTENSIONS),
                ))
            max_bytes = self._print3d_max_bytes()
            data = file.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise UserError(_('The file is too large (the limit is %s MB).', max_bytes // (1024 * 1024)))
            if not data:
                raise UserError(_('The file is empty.'))

            website = request.website
            partner = request.env.user.partner_id if not request.website.is_public_user() else False
            Estimate = request.env['print3d.estimate'].sudo().with_company(website.company_id)
            estimate = Estimate.create({
                'file': base64.b64encode(data),
                'filename': filename,
                'product_id': product_tmpl.product_variant_id.id,
                'company_id': website.company_id.id,
                'partner_id': partner.id if partner else False,
                'source': 'website',
            })
            material = self._print3d_materials().filtered(lambda m: str(m.id) == str(material_id or ''))
            if material and estimate.line_ids:
                estimate.line_ids.write({'material_id': material.id})
            return request.make_json_response(self._print3d_quote_values(estimate, quantity))
        except UserError as e:
            return request.make_json_response({'error': str(e)}, status=400)

    @http.route('/shop/3d-print-quote/update', type='jsonrpc', auth='public', website=True, sitemap=False)
    def print3d_quote_update(self, estimate_id, access_token, materials=None, quantity=1, **kwargs):
        estimate = self._print3d_get_estimate(estimate_id, access_token)
        if estimate.sale_line_ids:
            raise UserError(_('This quote is already in a cart. Upload the file again to change it.'))
        allowed = self._print3d_materials()
        for line_id, material_id in (materials or {}).items():
            line = estimate.line_ids.filtered(lambda l: str(l.id) == str(line_id))
            material = allowed.filtered(lambda m: str(m.id) == str(material_id))
            if line and material and line.material_id != material:
                line.material_id = material
        return self._print3d_quote_values(estimate, quantity)

    @http.route('/shop/3d-print-quote/add-to-cart', type='jsonrpc', auth='public', website=True, sitemap=False)
    def print3d_quote_add_to_cart(self, estimate_id, access_token, quantity=1, **kwargs):
        estimate = self._print3d_get_estimate(estimate_id, access_token)
        if estimate.state != 'done' or not estimate.price:
            raise UserError(_('This file could not be priced, so it cannot be added to the cart.'))
        quantity = max(int(quantity or 1), 1)
        order_sudo = request.cart or request.website._create_cart()
        if estimate.sale_line_ids - order_sudo.order_line:
            raise UserError(_('This quote has already been ordered. Please upload the file again.'))
        if not estimate.partner_id and order_sudo.partner_id != request.website.user_id.partner_id:
            estimate.partner_id = order_sudo.partner_id
        order_sudo._cart_add(
            product_id=estimate.product_id.id,
            quantity=quantity,
            print3d_estimate_id=estimate.id,
        )
        return {'redirect': '/shop/cart', 'cart_quantity': order_sudo.cart_quantity}

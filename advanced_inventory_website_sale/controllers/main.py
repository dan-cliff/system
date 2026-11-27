# -*- coding: utf-8 -*-
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale


def _collection_id(value):
    """The collection id from the ?collection= query value, or None."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


class WebsiteSaleCollection(WebsiteSale):
    """The shop's Collection filter: ?collection=<id> limits the products to that
    collection, and is kept by every shop link (categories, filters, pages)."""

    def _get_search_options(self, category=None, attribute_value_dict=None, tags=None, min_price=0.0,
                            max_price=0.0, conversion_rate=1, **post):
        options = super()._get_search_options(
            category=category, attribute_value_dict=attribute_value_dict, tags=tags, min_price=min_price,
            max_price=max_price, conversion_rate=conversion_rate, **post)
        options['collection'] = _collection_id(post.get('collection'))
        return options

    def _get_shop_domain(self, search, category, attribute_value_dict, search_in_description=True):
        domain = super()._get_shop_domain(search, category, attribute_value_dict, search_in_description)
        collection = _collection_id(request.httprequest.args.get('collection'))
        if collection:
            domain = Domain.AND([domain, Domain('collection_id', '=', collection)])
        return domain

    def _shop_get_query_url_kwargs(self, search, min_price, max_price, order=None, tags=None, **kwargs):
        values = super()._shop_get_query_url_kwargs(search, min_price, max_price, order=order, tags=tags, **kwargs)
        values['collection'] = _collection_id(kwargs.get('collection'))
        return values

    def _get_additional_shop_values(self, values, **kwargs):
        res = super()._get_additional_shop_values(values, **kwargs)
        if not request.website.is_view_active('advanced_inventory_website_sale.filter_products_collections'):
            return res
        website = request.website
        products = request.env['product.template'].sudo().search(Domain.AND([
            Domain(website.sale_product_domain()), Domain('collection_id', '!=', False)]))
        collections = products.collection_id.filtered(
            lambda c: not c.company_id or c.company_id == website.company_id).sorted()
        res.update({
            'all_collections': collections,
            'current_collection': _collection_id(kwargs.get('collection')),
        })
        return res

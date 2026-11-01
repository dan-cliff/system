# -*- coding: utf-8 -*-
from odoo import models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _search_get_detail(self, website, order, options):
        detail = super()._search_get_detail(website, order, options)
        collection = options.get('collection')
        if collection:
            # base_domain is a list of domains, all of which must match.
            detail['base_domain'] = list(detail['base_domain']) + [[('collection_id', '=', int(collection))]]
        return detail

# -*- coding: utf-8 -*-
"""Products follow the company hierarchy both ways.

Odoo lets a company see and use its own products, shared ones (no company)
and its parent companies' products. With Manufacturing, a parent company
also sees and uses its child companies' products (and theirs, all the way
down): in product fields (manufacturing orders, bills of materials,
components, ...) and in the Products views. Sibling and unrelated
companies' products stay out of reach.

Visibility comes from Odoo's "Product multi-company" record rule, which
data/product_company_data.xml widens the same way (the uninstall hook puts
Odoo's back); use comes from _check_company_domain below, which both the
company checks on save and the product pickers' filters use.
"""
from odoo import models
from odoo.orm.models import to_record_ids

ODOO_PRODUCT_RULE = "['|', ('company_id', 'parent_of', company_ids), ('company_id', '=', False)]"
FAMILY_PRODUCT_RULE = ("['|', '|', ('company_id', '=', False), ('company_id', 'parent_of', company_ids), "
                       "('company_id', 'child_of', company_ids)]")


def check_company_domain_family(self, companies):
    """Records with no company, or of one of these companies, a company above
    them or a company below them."""
    if isinstance(companies, str):
        return ['|', '|', ('company_id', '=', False), ('company_id', 'parent_of', companies),
                ('company_id', 'child_of', companies)]
    company_ids = to_record_ids(companies)
    if not company_ids:
        return [('company_id', '=', False)]
    Company = self.env['res.company'].sudo()
    selected = Company.browse(company_ids)
    family = {int(parent) for company in selected for parent in company.parent_path.split('/')[:-1]}
    family |= set(Company.with_context(active_test=False).search([('id', 'child_of', company_ids)]).ids)
    return [('company_id', 'in', sorted(family) + [False])]


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    _check_company_domain = check_company_domain_family


class ProductProduct(models.Model):
    _inherit = 'product.product'
    _check_company_domain = check_company_domain_family

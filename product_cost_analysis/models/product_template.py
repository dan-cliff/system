# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    cost_analysis_ids = fields.One2many(
        'product.cost.analysis',
        'product_tmpl_id',
        string='Cost Analyses',
    )
    cost_analysis_count = fields.Integer(
        string='Cost Analysis Count',
        compute='_compute_cost_analysis_count',
    )

    @api.depends('cost_analysis_ids')
    def _compute_cost_analysis_count(self):
        for tmpl in self:
            tmpl.cost_analysis_count = len(tmpl.cost_analysis_ids)

    def action_view_cost_analyses(self):
        self.ensure_one()
        return {
            'name': 'Cost Analyses',
            'type': 'ir.actions.act_window',
            'res_model': 'product.cost.analysis',
            'view_mode': 'list,form',
            'domain': [('product_tmpl_id', '=', self.id)],
            'context': {
                'default_product_tmpl_id': self.id,
                'default_name': self.name,
            },
        }


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def action_view_cost_analyses(self):
        """Delegate to the product template — required so Odoo 19 view
        validation passes when the smart button appears on product.product
        form views that inherit from the product.template form."""
        self.ensure_one()
        return self.product_tmpl_id.action_view_cost_analyses()

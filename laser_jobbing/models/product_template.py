# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    laser_template_id = fields.Many2one(
        'laser.template', string='Laser Template', index='btree_not_null',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help='Personalised with this laser template: every piece sold gets a laser job with its '
             'own text and pictures.',
    )
    laser_personalised = fields.Boolean(
        string='Laser Personalised', compute='_compute_laser_personalised', store=True,
    )

    @api.depends('laser_template_id')
    def _compute_laser_personalised(self):
        for product in self:
            product.laser_personalised = bool(product.laser_template_id)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    laser_template_id = fields.Many2one(related='product_tmpl_id.laser_template_id', store=True,
                                        index='btree_not_null')

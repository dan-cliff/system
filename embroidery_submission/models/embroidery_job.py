# -*- coding: utf-8 -*-
from odoo import fields, models


class EmbroideryJob(models.Model):
    _inherit = 'embroidery.job'

    submission_id = fields.Many2one('embroidery.submission', string='Submission', index='btree_not_null',
                                    readonly=True, copy=False,
                                    help='The submitted file this job was priced from.')
    sale_line_id = fields.Many2one('sale.order.line', string='Sales Order Line', index='btree_not_null',
                                   readonly=True, copy=False)
    sale_order_id = fields.Many2one(related='sale_line_id.order_id', string='Sales Order')

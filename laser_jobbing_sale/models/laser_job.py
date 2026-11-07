# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class LaserJob(models.Model):
    _inherit = 'laser.job'

    sale_line_ids = fields.One2many('sale.order.line', 'laser_job_id', string='Order Lines')
    sale_order_id = fields.Many2one(
        'sale.order', string='Sales Order', compute='_compute_sale_order_id', store=True, index='btree_not_null',
    )

    @api.depends('sale_line_ids.order_id')
    def _compute_sale_order_id(self):
        for job in self:
            job.sale_order_id = job.sudo().sale_line_ids[:1].order_id

    def action_view_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sales Order'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }

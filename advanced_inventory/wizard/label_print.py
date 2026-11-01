# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class AdvancedInventoryLabelPrint(models.TransientModel):
    """Print Labels: the products' labels from a label design (replaces Odoo's
    label layout wizard on products, variants and transfers)."""
    _name = 'advanced.inventory.label.print'
    _description = 'Print Labels'

    product_tmpl_ids = fields.Many2many('product.template', string='Products')
    product_ids = fields.Many2many('product.product', string='Variants')
    picking_ids = fields.Many2many('stock.picking', string='Transfers')
    label_template_id = fields.Many2one(
        'advanced.inventory.label.template', string='Label Design', required=True,
        domain="[('target', '=', 'product'), '|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
        default=lambda self: self._default_label_template())
    quantity_mode = fields.Selection(
        [('copies', 'Copies per product'), ('transfer', 'One per unit in the transfer')],
        string='How Many', required=True, default=lambda self: 'transfer' if self.env.context.get('default_picking_ids') else 'copies')
    copies = fields.Integer(string='Copies', default=1)
    variant_count = fields.Integer(compute='_compute_variant_count', string='Variants')
    label_count = fields.Integer(compute='_compute_variant_count', string='Labels')

    @api.model
    def _default_label_template(self):
        return self.env['advanced.inventory.label.template'].search([
            ('target', '=', 'product'), '|', ('company_id', '=', False), ('company_id', '=', self.env.company.id)],
            limit=1)

    def _variants(self):
        self.ensure_one()
        variants = self.product_ids | self.product_tmpl_ids.product_variant_ids
        if self.picking_ids:
            variants |= self.picking_ids.move_ids.product_id
        return variants.filtered(lambda p: p.type != 'service')

    def _copies(self):
        """{variant id: number of labels}."""
        self.ensure_one()
        if self.quantity_mode == 'transfer' and self.picking_ids:
            counts = {}
            for move in self.picking_ids.move_ids.filtered(lambda m: m.product_id.type != 'service'):
                qty = move.quantity or move.product_uom_qty
                qty = move.product_uom._compute_quantity(qty, move.product_id.uom_id, rounding_method='HALF-UP')
                counts[move.product_id.id] = counts.get(move.product_id.id, 0) + max(int(round(qty)), 0)
            return counts
        return {variant.id: max(self.copies, 0) for variant in self._variants()}

    @api.depends('product_ids', 'product_tmpl_ids', 'picking_ids', 'quantity_mode', 'copies')
    def _compute_variant_count(self):
        for wizard in self:
            wizard.variant_count = len(wizard._variants())
            wizard.label_count = sum(wizard._copies().values())

    @api.model
    def _open(self, context):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Print Labels'),
            'res_model': 'advanced.inventory.label.print',
            'view_mode': 'form',
            'views': [(self.env.ref('advanced_inventory.label_print_view_form').id, 'form')],
            'target': 'new',
            'context': dict(self.env.context, **context),
        }

    def action_print(self):
        self.ensure_one()
        variants = self._variants()
        copies = {k: v for k, v in self._copies().items() if v > 0}
        if not variants or not copies:
            raise UserError(self.env._('There are no labels to print.'))
        report = self.label_template_id.report_action_id
        return report.report_action(
            self.env['product.product'].browse(list(copies)),
            data={'inventory_label_copies': copies}, config=False)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def action_open_label_layout(self):
        if any(template.type == 'service' for template in self):
            raise UserError(self.env._('Labels cannot be printed for products of service type.'))
        return self.env['advanced.inventory.label.print']._open({'default_product_tmpl_ids': self.ids})


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.readonly
    def action_open_label_layout(self):
        if any(product.type == 'service' for product in self):
            raise UserError(self.env._('Labels cannot be printed for products of service type.'))
        return self.env['advanced.inventory.label.print']._open({'default_product_ids': self.ids})


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_open_label_layout(self):
        return self.env['advanced.inventory.label.print']._open({'default_picking_ids': self.ids})


# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # ── Costing (Product Cost Analysis) ───────────────────────────────────
    cost_analysis_id = fields.Many2one(
        'product.cost.analysis', string='Costing Analysis', copy=False,
        domain="[('product_tmpl_id', '=', id)]",
        help='The cost analysis that describes how this product is costed. With "Cost from '
             'Analysis" on, its variable cost per unit is the product\'s Cost, so stock '
             'valuation and margins use it.')
    cost_from_analysis = fields.Boolean(
        string='Cost from Analysis', copy=False,
        help='Keep the product\'s Cost equal to the costing analysis\' variable cost per unit.')
    analysis_unit_cost = fields.Monetary(related='cost_analysis_id.total_variable_cost', string='Analysed Unit Cost')
    analysis_fixed_cost = fields.Monetary(related='cost_analysis_id.total_fixed_cost', string='Analysed Fixed Costs')
    analysis_sell_price = fields.Monetary(related='cost_analysis_id.sell_price', string='Anticipated Sell Price')
    analysis_margin_percent = fields.Float(related='cost_analysis_id.margin_percent', string='Gross Margin (%)')
    analysis_break_even_units = fields.Integer(related='cost_analysis_id.break_even_units', string='Break-Even Units')
    analysis_break_even_progress = fields.Float(related='cost_analysis_id.break_even_progress',
                                                string='Break-Even Progress (%)')
    analysis_can_build_qty = fields.Float(related='cost_analysis_id.can_build_qty', string='Can Make')
    inventory_value = fields.Monetary(
        string='Stock Value', compute='_compute_inventory_value', currency_field='currency_id',
        help='Units on hand at the product\'s Cost.')
    inventory_potential_revenue = fields.Monetary(
        string='Potential Revenue', compute='_compute_inventory_value', currency_field='currency_id',
        help='Units on hand at the anticipated sell price (or the Sales Price without an analysis).')
    # ── Storage ───────────────────────────────────────────────────────────
    product_slot_ids = fields.One2many('advanced.inventory.product.slot', 'product_tmpl_id', string='Storage Slots')
    product_slot_count = fields.Integer(compute='_compute_product_slot_count', string='Slots')

    @api.depends('qty_available', 'standard_price', 'list_price', 'cost_analysis_id.sell_price')
    def _compute_inventory_value(self):
        for product in self:
            qty = product.qty_available if product.is_storable else 0.0
            price = product.cost_analysis_id.sell_price or product.list_price
            product.inventory_value = qty * product.standard_price
            product.inventory_potential_revenue = qty * price

    def _compute_product_slot_count(self):
        for product in self:
            product.product_slot_count = len(product.product_slot_ids)

    @api.onchange('cost_analysis_id')
    def _onchange_cost_analysis_id(self):
        if not self.cost_analysis_id:
            self.cost_from_analysis = False

    def write(self, vals):
        res = super().write(vals)
        if 'cost_analysis_id' in vals or vals.get('cost_from_analysis'):
            self.filtered('cost_from_analysis')._apply_analysis_cost()
        return res

    def _apply_analysis_cost(self):
        """Set the Cost of the products (all their variants) from their costing analysis."""
        for product in self.filtered(lambda p: p.cost_from_analysis and p.cost_analysis_id):
            cost = product.cost_analysis_id.total_variable_cost
            currency = product.cost_analysis_id.currency_id
            company_currency = (product.company_id or self.env.company).currency_id
            if currency and company_currency and currency != company_currency:
                cost = currency._convert(cost, company_currency, product.company_id or self.env.company,
                                         fields.Date.context_today(self))
            variants = product.product_variant_ids.filtered(
                lambda v: company_currency.compare_amounts(v.standard_price, cost) != 0)
            if variants:
                variants.write({'standard_price': cost})

    def action_view_product_slots(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_inventory.action_product_slot')
        action['domain'] = [('product_tmpl_id', '=', self.id)]
        action['context'] = {'default_product_id': self.product_variant_id.id}
        return action


class ProductProduct(models.Model):
    _inherit = 'product.product'

    product_slot_ids = fields.One2many('advanced.inventory.product.slot', 'product_id', string='Storage Slots')

    def action_view_product_slots(self):
        self.ensure_one()
        action = self.product_tmpl_id.action_view_product_slots()
        action['domain'] = [('product_id', '=', self.id)]
        action['context'] = {'default_product_id': self.id}
        return action


class ProductCostAnalysis(models.Model):
    _inherit = 'product.cost.analysis'

    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True, default=lambda self: self.env.company,
        tracking=True)
    qty_on_hand = fields.Float(related='product_tmpl_id.qty_available', string='On Hand')
    is_product_cost = fields.Boolean(
        string='Sets the Product Cost', compute='_compute_is_product_cost',
        help='The product takes its Cost from this analysis.')
    stock_value = fields.Monetary(
        string='Stock Value', compute='_compute_stock_figures', currency_field='currency_id',
        help='Units on hand at this analysis\' variable cost per unit.')
    stock_margin = fields.Monetary(
        string='Margin on Stock', compute='_compute_stock_figures', currency_field='currency_id',
        help='What the units on hand would earn over their variable cost at the anticipated sell price.')
    can_build_qty = fields.Float(
        string='Can Make', compute='_compute_stock_figures', digits=(16, 0),
        help='Units the material components on hand can make (the scarcest component decides).')
    limiting_component_id = fields.Many2one(
        'product.product', string='Scarcest Component', compute='_compute_stock_figures')
    units_delivered = fields.Float(
        string='Units Delivered', compute='_compute_stock_figures', digits='Product Unit',
        help='Units delivered to customers (less returns) since this analysis was created.')
    break_even_progress = fields.Float(
        string='Break-Even Progress (%)', compute='_compute_stock_figures', digits=(16, 1),
        help='Units delivered as a share of the break-even units.')
    units_to_break_even = fields.Float(
        string='Units to Break-Even', compute='_compute_stock_figures', digits=(16, 0))
    outdated_line_count = fields.Integer(
        string='Outdated Costs', compute='_compute_stock_figures',
        help='Material lines whose unit cost differs from the component\'s current Cost in Inventory.')

    def _compute_is_product_cost(self):
        for analysis in self:
            product = analysis.product_tmpl_id
            analysis.is_product_cost = bool(product.cost_from_analysis and product.cost_analysis_id == analysis)

    @api.depends('product_tmpl_id', 'total_variable_cost', 'sell_price', 'cost_line_ids.quantity',
                 'cost_line_ids.unit_cost', 'cost_line_ids.material_product_id', 'break_even_units')
    def _compute_stock_figures(self):
        moves_by_product = {}
        products = self.product_tmpl_id.product_variant_ids
        if products and self.ids:
            first = min(self.mapped('create_date') or [fields.Datetime.now()])
            moves = self.env['stock.move'].sudo().search([
                ('product_id', 'in', products.ids), ('state', '=', 'done'), ('date', '>=', first),
                '|', ('location_dest_id.usage', '=', 'customer'), ('location_id.usage', '=', 'customer')])
            for move in moves:
                sign = 1 if move.location_dest_id.usage == 'customer' else -1
                moves_by_product.setdefault(move.product_id.product_tmpl_id.id, []).append(
                    (move.date, sign * move.product_qty))
        for analysis in self:
            qty = analysis.product_tmpl_id.qty_available
            analysis.stock_value = qty * analysis.total_variable_cost
            analysis.stock_margin = qty * (analysis.sell_price - analysis.total_variable_cost)
            makeable, scarcest = None, self.env['product.product']
            outdated = 0
            for line in analysis.cost_line_ids.filtered('material_product_id'):
                component = line.material_product_id
                if line.cost_type == 'material' and component.currency_id.compare_amounts(
                        line.unit_cost, component.standard_price) != 0:
                    outdated += 1
                if line.is_once_off or line.quantity <= 0 or not component.is_storable:
                    continue
                can = component.qty_available // line.quantity
                if makeable is None or can < makeable:
                    makeable, scarcest = can, component
            analysis.can_build_qty = max(makeable or 0.0, 0.0)
            analysis.limiting_component_id = scarcest
            analysis.outdated_line_count = outdated
            since = analysis.create_date or fields.Datetime.now()
            delivered = sum(q for date, q in moves_by_product.get(analysis.product_tmpl_id.id, []) if date >= since)
            analysis.units_delivered = delivered
            if analysis.break_even_units:
                analysis.break_even_progress = min(delivered / analysis.break_even_units * 100.0, 100.0)
                analysis.units_to_break_even = max(analysis.break_even_units - delivered, 0.0)
            else:
                analysis.break_even_progress = 100.0 if analysis.is_viable else 0.0
                analysis.units_to_break_even = 0.0

    # ── Keeping the product's Cost in step ────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        analyses = super().create(vals_list)
        analyses._sync_product_cost()
        return analyses

    def write(self, vals):
        res = super().write(vals)
        self._sync_product_cost()
        return res

    def _sync_product_cost(self):
        products = self.env['product.template'].search([
            ('cost_analysis_id', 'in', self.ids), ('cost_from_analysis', '=', True)])
        products._apply_analysis_cost()

    def action_use_as_product_cost(self):
        """Make this analysis the product's costing analysis and take its Cost from it."""
        self.ensure_one()
        if not self.is_viable and not self.total_variable_cost:
            raise UserError(_('Add the cost lines first: the analysis has no cost per unit yet.'))
        self.product_tmpl_id.sudo().write({'cost_analysis_id': self.id, 'cost_from_analysis': True})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('%(product)s now costs %(cost)s a unit, from this analysis.',
                             product=self.product_tmpl_id.display_name,
                             cost=self.currency_id.format(self.total_variable_cost)),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_refresh_material_costs(self):
        """Update the material lines' unit costs from the components' current Cost
        in Inventory (which may itself come from the component's own analysis)."""
        for analysis in self:
            for line in analysis.cost_line_ids.filtered(lambda l: l.material_product_id and l.cost_type == 'material'):
                if line.unit_cost != line.material_product_id.standard_price:
                    line.unit_cost = line.material_product_id.standard_price
        return True

    def action_view_components(self):
        self.ensure_one()
        components = self.cost_line_ids.material_product_id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Components of %s', self.name),
            'res_model': 'product.product',
            'view_mode': 'list,form',
            'domain': [('id', 'in', components.ids)],
        }


class ProductCostAnalysisLine(models.Model):
    _inherit = 'product.cost.analysis.line'

    material_qty_on_hand = fields.Float(related='material_product_id.qty_available', string='On Hand')
    material_current_cost = fields.Float(related='material_product_id.standard_price', string='Current Cost')

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.analysis_id._sync_product_cost()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if {'quantity', 'unit_cost', 'is_once_off', 'analysis_id'} & set(vals):
            self.analysis_id._sync_product_cost()
        return res

    def unlink(self):
        analyses = self.analysis_id
        res = super().unlink()
        analyses.exists()._sync_product_cost()
        return res

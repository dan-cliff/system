# -*- coding: utf-8 -*-
import math
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class ProductCostAnalysis(models.Model):
    _name = 'product.cost.analysis'
    _description = 'Product Cost Analysis'
    _order = 'product_tmpl_id, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ── Identity ───────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Analysis Name',
        required=True,
        help='A short label to distinguish this analysis from others on the same product '
             '(e.g. "Base model — AUD" or "Premium bundle Q1 2025").',
    )
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product',
        required=True,
        ondelete='cascade',
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    sell_price = fields.Monetary(
        string='Anticipated Sell Price',
        currency_field='currency_id',
        help='The price per unit at which the product is expected to be sold. '
             'Auto-filled from the product\'s sales price when the product is selected.',
    )

    # ── Bill of Materials link ─────────────────────────────────────────────────
    bom_id = fields.Many2one(
        'mrp.bom',
        string='Bill of Materials',
        domain="[('product_tmpl_id', '=', product_tmpl_id)]",
        ondelete='set null',
        help='Select a Bill of Materials to import component and operation costs automatically.',
    )

    notes = fields.Text(
        string='Notes',
        help='Optional remarks or assumptions underpinning this analysis.',
    )
    cost_line_ids = fields.One2many(
        'product.cost.analysis.line',
        'analysis_id',
        string='Cost Lines',
    )

    # ── Computed totals ────────────────────────────────────────────────────────
    total_fixed_cost = fields.Monetary(
        string='Total Fixed Costs',
        compute='_compute_totals',
        currency_field='currency_id',
        store=True,
        help='Sum of all once-off (fixed) cost lines.',
    )
    total_variable_cost = fields.Monetary(
        string='Total Variable Cost (per Unit)',
        compute='_compute_totals',
        currency_field='currency_id',
        store=True,
        help='Sum of all per-unit (variable) cost lines for a single unit.',
    )
    contribution_margin = fields.Monetary(
        string='Contribution Margin (per Unit)',
        compute='_compute_totals',
        currency_field='currency_id',
        store=True,
        help='Sell price minus total variable cost per unit. '
             'This is the amount each unit sold contributes toward recovering fixed costs and generating profit.',
    )
    margin_percent = fields.Float(
        string='Gross Margin (%)',
        compute='_compute_totals',
        digits=(16, 2),
        store=True,
        help='Contribution margin as a percentage of the sell price.',
    )
    break_even_units = fields.Integer(
        string='Break-Even Units',
        compute='_compute_totals',
        store=True,
        help='Minimum number of units that must be sold to recover all fixed costs.',
    )
    break_even_display = fields.Char(
        string='Break-Even',
        compute='_compute_totals',
        store=True,
        help='Human-readable break-even result.',
    )
    total_investment = fields.Monetary(
        string='Total Investment at Break-Even',
        compute='_compute_totals',
        currency_field='currency_id',
        store=True,
        help='Total cost (fixed + variable) at the break-even unit quantity.',
    )
    is_viable = fields.Boolean(
        string='Viable',
        compute='_compute_totals',
        store=True,
        help='True when the sell price exceeds per-unit costs (positive contribution margin).',
    )

    # ── Profitability grid controls ────────────────────────────────────────────
    profitability_num_rows = fields.Integer(
        string='Number of Rows',
        default=10,
        help='Total rows shown in the Profitability Analysis table, including the break-even row.',
    )
    profitability_factor = fields.Integer(
        string='Multiplication Factor',
        default=50,
        help='Row 2 starts at the next multiple of this value above the break-even quantity; '
             'each subsequent row increases by this same factor.',
    )

    # ── Profitability grid (computed HTML) ─────────────────────────────────────
    profitability_table_html = fields.Html(
        string='Profitability Analysis',
        compute='_compute_profitability_table',
        sanitize=False,
        store=False,
        help='Auto-generated table showing revenue, costs and net profit at the break-even '
             'quantity and a range of sales volumes above it.',
    )

    # ── Auto-name helper ──────────────────────────────────────────────────────
    def _build_analysis_name(self):
        """Return a formatted name: 'Product - BoM (Price)'."""
        parts = []
        if self.product_tmpl_id:
            parts.append(self.product_tmpl_id.name)
        if self.bom_id:
            parts.append(self.bom_id.display_name)

        base = ' - '.join(parts)

        if self.sell_price:
            cur = self.currency_id
            symbol = cur.symbol or ''
            if cur.position == 'before':
                price_str = f'{symbol}{self.sell_price:,.2f}'
            else:
                price_str = f'{self.sell_price:,.2f} {symbol}'
            base = f'{base} ({price_str})' if base else f'({price_str})'

        return base

    # ── Onchange: auto-fill sell price and BoM when product is selected ────────
    @api.onchange('product_tmpl_id')
    def _onchange_product_tmpl_id(self):
        if not self.product_tmpl_id:
            return
        # Auto-fill sell price from the product's public sales price
        self.sell_price = self.product_tmpl_id.list_price
        # Clear BoM if it no longer matches the new product
        if self.bom_id and self.bom_id.product_tmpl_id != self.product_tmpl_id:
            self.bom_id = False
        # Auto-select the BoM if exactly one exists for this product
        if not self.bom_id:
            boms = self.env['mrp.bom'].search([
                ('product_tmpl_id', '=', self.product_tmpl_id.id),
                ('active', '=', True),
            ])
            if len(boms) == 1:
                self.bom_id = boms[0]
        # Update auto-formatted name (sell_price already set above)
        self.name = self._build_analysis_name()

    # ── Onchange: refresh name when BoM changes ───────────────────────────────
    @api.onchange('bom_id')
    def _onchange_bom_id(self):
        self.name = self._build_analysis_name()

    # ── Onchange: refresh name when sell price changes ────────────────────────
    @api.onchange('sell_price')
    def _onchange_sell_price(self):
        self.name = self._build_analysis_name()

    # ── Import from Bill of Materials ──────────────────────────────────────────
    def action_import_from_bom(self):
        """Clear current cost lines and re-import them from the linked BoM."""
        self.ensure_one()

        if not self.product_tmpl_id:
            raise UserError(_("Please select a product before importing from a Bill of Materials."))
        if not self.bom_id:
            raise UserError(_("Please select a Bill of Materials to import from."))

        bom = self.bom_id
        bom_qty = bom.product_qty or 1.0  # quantity of finished product this BoM produces

        # Remove existing lines
        self.cost_line_ids.unlink()

        vals_list = []
        seq = 10

        # ── Material components ────────────────────────────────────────────────
        for line in bom.bom_line_ids:
            product = line.product_id
            # Scale qty to per finished unit
            per_unit_qty = line.product_qty / bom_qty
            vals_list.append({
                'analysis_id': self.id,
                'sequence': seq,
                'name': product.display_name,
                'cost_type': 'material',
                'is_once_off': False,   # materials recur for every unit produced
                'quantity': per_unit_qty,
                'unit_cost': product.standard_price,
                'material_product_id': product.id,
            })
            seq += 10

        # ── Work centre operations ─────────────────────────────────────────────
        for operation in bom.operation_ids:
            wc = operation.workcenter_id
            # time_cycle_manual is in minutes; scale to hours per finished unit
            per_unit_hours = (operation.time_cycle_manual / 60.0) / bom_qty
            vals_list.append({
                'analysis_id': self.id,
                'sequence': seq,
                'name': operation.name,
                'cost_type': 'labour',
                'is_once_off': False,   # production time recurs for every unit
                'quantity': round(per_unit_hours, 4),
                'unit_cost': wc.costs_hour,
                'workcenter_id': wc.id,
            })
            seq += 10

        if vals_list:
            self.env['product.cost.analysis.line'].create(vals_list)
        else:
            raise UserError(_(
                "The selected Bill of Materials has no components or operations to import."
            ))

        return True

    # ── Totals computation ─────────────────────────────────────────────────────
    @api.depends(
        'sell_price',
        'cost_line_ids.line_total',
        'cost_line_ids.is_once_off',
    )
    def _compute_totals(self):
        for rec in self:
            fixed = sum(l.line_total for l in rec.cost_line_ids if l.is_once_off)
            variable = sum(l.line_total for l in rec.cost_line_ids if not l.is_once_off)
            margin = rec.sell_price - variable

            rec.total_fixed_cost = fixed
            rec.total_variable_cost = variable
            rec.contribution_margin = margin
            rec.margin_percent = (margin / rec.sell_price * 100) if rec.sell_price else 0.0

            if margin > 0:
                rec.is_viable = True
                if fixed > 0:
                    beu = math.ceil(fixed / margin)
                    rec.break_even_units = beu
                    rec.total_investment = fixed + beu * variable
                    rec.break_even_display = f'{beu:,} units'
                else:
                    rec.break_even_units = 0
                    rec.total_investment = 0.0
                    rec.break_even_display = 'Profitable from unit 1 (no fixed costs)'
            else:
                rec.is_viable = False
                rec.break_even_units = 0
                rec.total_investment = 0.0
                rec.break_even_display = 'Cannot break even — per-unit costs ≥ sell price'

    # ── Profitability analysis grid ────────────────────────────────────────────
    @api.depends(
        'sell_price', 'total_fixed_cost', 'total_variable_cost',
        'break_even_units', 'is_viable', 'currency_id', 'cost_line_ids',
        'profitability_num_rows', 'profitability_factor',
    )
    def _compute_profitability_table(self):
        for rec in self:
            if not rec.is_viable or not rec.sell_price or not rec.cost_line_ids:
                rec.profitability_table_html = False
                continue

            fixed = rec.total_fixed_cost
            variable = rec.total_variable_cost
            sell = rec.sell_price
            beu = rec.break_even_units  # 0 means "profitable from unit 1 — no fixed costs"

            factor = max(rec.profitability_factor or 1, 1)
            num_rows = max(rec.profitability_num_rows or 1, 1)

            # Row 1: break-even point (show as 1 when BEU=0, i.e. no fixed costs)
            display_beu = beu if beu > 0 else 1
            units_list = [display_beu]

            # Rows 2‥num_rows: next multiple of factor above break-even, stepping by factor
            if num_rows > 1:
                start = math.ceil((display_beu + 1) / factor) * factor
                for i in range(num_rows - 1):
                    units_list.append(start + i * factor)

            def fmt(val, env=rec.env, cur=rec.currency_id):
                return formatLang(env, val, currency_obj=cur)

            rows_html = ''
            for idx, units in enumerate(units_list):
                revenue = units * sell
                var_costs = units * variable
                total_cost = fixed + var_costs
                profit = revenue - total_cost

                profit_cls = 'text-success fw-bold' if profit >= 0 else 'text-danger fw-bold'
                be_badge = (
                    ' <span class="badge rounded-pill text-bg-warning ms-2"'
                    ' style="font-size:0.7em;vertical-align:middle;">Break-Even</span>'
                    if idx == 0 else ''
                )

                rows_html += (
                    f'<tr>'
                    f'<td class="text-end">{units:,}{be_badge}</td>'
                    f'<td class="text-end">{fmt(revenue)}</td>'
                    f'<td class="text-end">{fmt(var_costs)}</td>'
                    f'<td class="text-end">{fmt(fixed)}</td>'
                    f'<td class="text-end">{fmt(total_cost)}</td>'
                    f'<td class="text-end {profit_cls}">{fmt(profit)}</td>'
                    f'</tr>'
                )

            rec.profitability_table_html = (
                '<table class="table table-sm table-bordered table-hover mb-0">'
                '<thead class="table-secondary">'
                '<tr>'
                '<th class="text-end">Units Sold</th>'
                '<th class="text-end">Revenue</th>'
                '<th class="text-end">Variable Costs</th>'
                '<th class="text-end">Fixed Costs</th>'
                '<th class="text-end">Total Costs</th>'
                '<th class="text-end">Net Profit / (Loss)</th>'
                '</tr>'
                '</thead>'
                f'<tbody>{rows_html}</tbody>'
                '</table>'
            )


class ProductCostAnalysisLine(models.Model):
    _name = 'product.cost.analysis.line'
    _description = 'Product Cost Analysis Line'
    _order = 'sequence, id'

    analysis_id = fields.Many2one(
        'product.cost.analysis',
        string='Analysis',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Description', required=True)
    cost_type = fields.Selection([
        ('material', 'Material'),
        ('labour', 'Labour'),
        ('overhead', 'Overhead'),
        ('other', 'Other'),
    ], string='Type', required=True, default='material')
    is_once_off = fields.Boolean(
        string='Once-Off',
        default=False,
        help='Tick if this is a one-time fixed cost (e.g. tooling, mould, development). '
             'Leave unticked if this cost is incurred for every unit produced or sold.',
    )
    quantity = fields.Float(
        string='Qty / Hours',
        digits=(16, 4),
        default=1.0,
        help='Number of units of material, or hours of labour required per finished unit.',
    )
    unit_cost = fields.Monetary(
        string='Unit Cost / Rate',
        currency_field='currency_id',
        help='Cost per unit of material, or hourly rate for labour.',
    )
    currency_id = fields.Many2one(
        related='analysis_id.currency_id',
        string='Currency',
        store=True,
    )
    line_total = fields.Monetary(
        string='Line Total',
        compute='_compute_line_total',
        currency_field='currency_id',
        store=True,
    )

    # ── Integration links (optional, for auto-filling costs) ──────────────────
    material_product_id = fields.Many2one(
        'product.product',
        string='Component Product',
        ondelete='set null',
        help='Link to a product to auto-fill the unit cost from its standard (cost) price.',
    )
    workcenter_id = fields.Many2one(
        'mrp.workcenter',
        string='Work Centre',
        ondelete='set null',
        help='Link to a work centre to auto-fill the hourly rate from its cost-per-hour setting.',
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        ondelete='set null',
        help='Link to an employee to auto-fill the hourly rate from their contract hourly cost.',
    )

    # ── Line total ─────────────────────────────────────────────────────────────
    @api.depends('quantity', 'unit_cost')
    def _compute_line_total(self):
        for line in self:
            line.line_total = line.quantity * line.unit_cost

    # ── Onchange: auto-fill name and cost from component product ──────────────
    @api.onchange('material_product_id')
    def _onchange_material_product_id(self):
        if self.material_product_id:
            self.name = self.material_product_id.display_name
            self.cost_type = 'material'
            self.unit_cost = self.material_product_id.standard_price
            # Clear the other integration links
            self.workcenter_id = False
            self.employee_id = False

    # ── Onchange: auto-fill hourly rate from work centre ─────────────────────
    @api.onchange('workcenter_id')
    def _onchange_workcenter_id(self):
        if self.workcenter_id:
            self.cost_type = 'labour'
            self.unit_cost = self.workcenter_id.costs_hour
            if not self.name:
                self.name = self.workcenter_id.name
            # Clear the other integration links
            self.material_product_id = False
            self.employee_id = False

    # ── Onchange: auto-fill hourly rate from employee ─────────────────────────
    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            self.cost_type = 'labour'
            self.unit_cost = self.employee_id.hourly_cost
            if not self.name:
                self.name = self.employee_id.name
            # Clear the other integration links
            self.material_product_id = False
            self.workcenter_id = False

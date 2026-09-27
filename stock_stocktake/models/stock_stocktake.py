from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class StockStocktake(models.Model):
    _name = 'stock.stocktake'
    _description = 'Stocktake'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(default='New', copy=False, readonly=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, tracking=True,
        default=lambda self: self.env.company,
    )
    user_id = fields.Many2one(
        'res.users', string='Counted By', tracking=True,
        default=lambda self: self.env.user,
    )
    date = fields.Datetime(default=fields.Datetime.now, required=True, tracking=True)
    state = fields.Selection(
        [('draft', 'In Progress'), ('done', 'Completed')],
        default='draft', required=True, copy=False, tracking=True,
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Warehouse', tracking=True,
        domain="[('company_id', '=', company_id)]",
        help='Only shown when the Inventory app\'s Warehouses feature is enabled. '
             'Stock is only adjusted for this warehouse\'s stock location.',
    )
    location_id = fields.Many2one(
        'stock.location', string='Location', tracking=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', (company_id, False)),"
               " '|', ('warehouse_id', '=', warehouse_id), ('warehouse_id', '=', False)]",
        help='Only shown when the Inventory app\'s Storage Locations feature is enabled. '
             'Stock is only adjusted for this location.',
    )
    line_ids = fields.One2many('stock.stocktake.line', 'stocktake_id', string='Lines')
    line_count = fields.Integer(compute='_compute_line_count')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for stocktake in self:
            stocktake.line_count = len(stocktake.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('stock.stocktake') or 'New'
        return super().create(vals_list)

    @api.constrains('warehouse_id', 'location_id')
    def _check_warehouse_location_required(self):
        for stocktake in self:
            if self.env.user.has_group('stock.group_stock_multi_warehouses') and not stocktake.warehouse_id:
                raise ValidationError('Warehouses are enabled for this company - please select a Warehouse.')
            if self.env.user.has_group('stock.group_stock_multi_locations') and not stocktake.location_id:
                raise ValidationError('Storage Locations are enabled for this company - please select a Location.')

    @api.model
    def get_required_fields(self):
        """Whether a new stocktake needs a Warehouse and/or Location filled in, based on
        whether those Inventory app features are enabled - used by quick-create UIs
        (e.g. the Scanner app) to decide whether to prompt for them up front."""
        return {
            'need_warehouse': self.env.user.has_group('stock.group_stock_multi_warehouses'),
            'need_location': self.env.user.has_group('stock.group_stock_multi_locations'),
        }

    def _get_target_location(self):
        """Resolve the single stock.location whose on-hand quantity this stocktake adjusts,
        respecting whether the Warehouses/Locations features are enabled."""
        self.ensure_one()
        if self.location_id:
            return self.location_id
        if self.warehouse_id:
            return self.warehouse_id.lot_stock_id
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.company_id.id)], limit=1)
        return warehouse.lot_stock_id

    def action_scan_barcode(self, barcode, lot_name=None):
        """Find-or-create the line for a scanned product (+ lot/serial) and add one to its
        counted quantity. Returns a dict describing the outcome for the scanning screen."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('This stocktake is already completed.')

        product = self.env['product.product'].search(
            [('barcode', '=', barcode), ('company_id', 'in', (self.company_id.id, False))], limit=1)
        if not product:
            return {'error': 'No product found for barcode "%s".' % barcode}

        lot = self.env['stock.lot']
        if product.tracking != 'none':
            if not lot_name:
                return {'needs_lot': True, 'product_id': product.id, 'product_name': product.display_name}
            lot = self.env['stock.lot'].search([
                ('product_id', '=', product.id),
                ('company_id', '=', self.company_id.id),
                ('name', '=', lot_name),
            ], limit=1)
            if not lot:
                lot = self.env['stock.lot'].create({
                    'product_id': product.id,
                    'company_id': self.company_id.id,
                    'name': lot_name,
                })

        line = self.line_ids.filtered(
            lambda l: l.product_id == product and l.lot_id == lot)
        if line:
            line.counted_qty += 1
        else:
            line = self.env['stock.stocktake.line'].create({
                'stocktake_id': self.id,
                'product_id': product.id,
                'lot_id': lot.id or False,
                'counted_qty': 1,
            })
        return {'line_id': line.id}

    def action_set_line_qty(self, line_id, qty):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('This stocktake is already completed.')
        line = self.env['stock.stocktake.line'].browse(line_id)
        if line.stocktake_id != self:
            raise UserError('This line does not belong to this stocktake.')
        line.counted_qty = qty
        return {'line_id': line.id}

    def action_confirm_complete(self):
        for stocktake in self:
            if stocktake.state != 'draft':
                continue
            location = stocktake._get_target_location()
            if not location:
                raise UserError('Could not determine a stock location to adjust for %s.' % stocktake.name)
            quants = self.env['stock.quant']
            for line in stocktake.line_ids:
                quant = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', location.id),
                    ('lot_id', '=', line.lot_id.id if line.lot_id else False),
                    ('company_id', '=', stocktake.company_id.id),
                ], limit=1)
                if not quant:
                    quant = self.env['stock.quant'].create({
                        'product_id': line.product_id.id,
                        'location_id': location.id,
                        'lot_id': line.lot_id.id if line.lot_id else False,
                        'company_id': stocktake.company_id.id,
                    })
                quant.inventory_quantity = line.counted_qty
                quants |= quant
            quants.action_apply_inventory()
            stocktake.state = 'done'
        return True

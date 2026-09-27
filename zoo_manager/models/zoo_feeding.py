from collections import defaultdict

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class ZooFeeding(models.Model):
    _name = 'zoo.feeding'
    _description = 'Feeding Round'
    _inherit = ['mail.thread']
    _order = 'scheduled_datetime desc, id desc'

    enclosure_id = fields.Many2one('zoo.enclosure', required=True, index=True, tracking=True)
    animal_ids = fields.Many2many(
        'zoo.animal', 'zoo_animal_feeding_rel', 'feeding_id', 'animal_id', string='Animals',
        compute='_compute_animal_ids', store=True, readonly=False,
        domain="[('enclosure_id', '=', enclosure_id), ('state', '=', 'present')]",
    )
    scheduled_datetime = fields.Datetime(string='Scheduled', required=True, default=fields.Datetime.now)
    fed_datetime = fields.Datetime(string='Fed At', readonly=True, copy=False)
    user_id = fields.Many2one('res.users', string='Keeper', default=lambda self: self.env.user, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    feed_warehouse_ids = fields.Many2many('stock.warehouse', compute='_compute_feed_warehouse_ids')
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Feed From', tracking=True,
        default=lambda self: self._default_warehouse_id(),
        domain="[('id', 'in', feed_warehouse_ids)] if feed_warehouse_ids else [('company_id', '=', company_id)]",
        help='Warehouse the food is taken from when the round is marked Fed.',
    )
    line_ids = fields.One2many(
        'zoo.feeding.line', 'feeding_id', string='Food Given', copy=True,
        help='Filled in from the animals\' diets; adjust to what was actually given.',
    )
    move_ids = fields.One2many('stock.move', 'zoo_feeding_id', string='Stock Moves', readonly=True)
    move_count = fields.Integer(compute='_compute_move_count')
    consumption_id = fields.Many2one('zoo.feeding.consumption', string='Consumption', tracking=True)
    consumption_refused = fields.Boolean(related='consumption_id.refused')
    notes = fields.Text()
    state = fields.Selection(
        [('planned', 'Planned'), ('done', 'Fed'), ('cancelled', 'Cancelled')],
        default='planned', required=True, tracking=True, copy=False,
    )

    @api.model
    def _default_warehouse_id(self):
        company = self.env.company
        return company.zoo_feed_warehouse_ids[:1] or self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1,
        )

    @api.depends('company_id')
    def _compute_feed_warehouse_ids(self):
        for feeding in self:
            feeding.feed_warehouse_ids = feeding.company_id.zoo_feed_warehouse_ids

    @api.depends('enclosure_id')
    def _compute_animal_ids(self):
        for feeding in self:
            feeding.animal_ids = feeding.enclosure_id.animal_ids.filtered(lambda a: a.state == 'present')

    @api.depends('move_ids')
    def _compute_move_count(self):
        for feeding in self:
            feeding.move_count = len(feeding.move_ids)

    @api.depends('enclosure_id', 'scheduled_datetime')
    def _compute_display_name(self):
        for feeding in self:
            when = fields.Datetime.context_timestamp(feeding, feeding.scheduled_datetime).strftime('%d/%m/%Y %H:%M') if feeding.scheduled_datetime else ''
            feeding.display_name = f'{feeding.enclosure_id.display_name or ""} {when}'.strip()

    def _diet_line_commands(self):
        """Food lines for the animals being fed: each diet product once, with
        the per-feed quantities of all the animals added up."""
        self.ensure_one()
        quantities = defaultdict(float)
        for animal in self.animal_ids:
            for diet_line in animal.diet_id.line_ids.filtered('product_id'):
                quantities[diet_line.product_id] += diet_line.quantity
        return [Command.clear()] + [
            Command.create({'product_id': product.id, 'quantity': quantity})
            for product, quantity in quantities.items()
        ]

    @api.onchange('animal_ids')
    def _onchange_animal_ids_fill_food(self):
        if self.state == 'planned':
            self.line_ids = self._diet_line_commands()

    @api.model_create_multi
    def create(self, vals_list):
        feedings = super().create(vals_list)
        for feeding, vals in zip(feedings, vals_list):
            if 'line_ids' not in vals and feeding.animal_ids:
                feeding.line_ids = feeding._diet_line_commands()
        return feedings

    def action_fill_from_diets(self):
        for feeding in self.filtered(lambda f: f.state == 'planned'):
            feeding.line_ids = feeding._diet_line_commands()

    def _stock_lines(self):
        """Food lines that change stock: storable products with a quantity."""
        return self.line_ids.filtered(
            lambda l: l.product_id.is_storable
            and not float_is_zero(l.quantity, precision_rounding=l.product_id.uom_id.rounding)
        )

    def _move_feed(self, lines, location, location_dest):
        moves = self.env['stock.move'].sudo().create([{
            'origin': self.display_name,
            'company_id': self.company_id.id,
            'product_id': line.product_id.id,
            'product_uom': line.product_id.uom_id.id,
            'product_uom_qty': line.quantity,
            'location_id': location.id,
            'location_dest_id': location_dest.id,
            'zoo_feeding_id': self.id,
            'move_line_ids': [Command.create({
                'product_id': line.product_id.id,
                'product_uom_id': line.product_id.uom_id.id,
                'quantity': line.quantity,
                'location_id': location.id,
                'location_dest_id': location_dest.id,
            })],
            'picked': True,
        } for line in lines])
        moves._action_done()
        return moves

    def action_mark_fed(self):
        for feeding in self.filtered(lambda f: f.state == 'planned'):
            lines = feeding._stock_lines()
            if lines:
                if not feeding.warehouse_id:
                    raise UserError(self.env._('Choose the warehouse the food is taken from (Feed From).'))
                feeding._move_feed(
                    lines, feeding.warehouse_id.lot_stock_id, feeding.company_id._zoo_feed_location(),
                )
            feeding.write({'state': 'done', 'fed_datetime': fields.Datetime.now(), 'user_id': self.env.user.id})

    def _return_feed(self):
        """Put back the stock taken when the round was marked Fed."""
        for feeding in self.filtered(lambda f: f.state == 'done'):
            taken = defaultdict(float)
            for move in feeding.move_ids.filtered(lambda m: m.state == 'done'):
                sign = 1 if move.location_dest_id == feeding.company_id.zoo_feed_location_id else -1
                taken[(move.product_id, move.location_id if sign > 0 else move.location_dest_id)] += sign * move.quantity
            for (product, stock_location), quantity in taken.items():
                if float_is_zero(quantity, precision_rounding=product.uom_id.rounding):
                    continue
                line = self.env['zoo.feeding.line'].new({'product_id': product.id, 'quantity': quantity})
                feeding._move_feed(line, feeding.company_id.zoo_feed_location_id, stock_location)

    def action_cancel(self):
        self._return_feed()
        self.write({'state': 'cancelled'})

    def action_reset_to_planned(self):
        self._return_feed()
        self.write({'state': 'planned', 'fed_datetime': False})

    def action_view_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Stock Moves'),
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [('zoo_feeding_id', '=', self.id)],
        }


class ZooFeedingLine(models.Model):
    _name = 'zoo.feeding.line'
    _description = 'Feeding Round Food'
    _order = 'feeding_id, id'

    feeding_id = fields.Many2one('zoo.feeding', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one(
        'product.product', string='Food', required=True,
        domain="product_domain",
        help='Only products matching the Feeds settings are offered.',
    )
    product_domain = fields.Binary(compute='_compute_product_domain')
    quantity = fields.Float(digits='Product Unit')
    uom_id = fields.Many2one(related='product_id.uom_id', string='Unit')
    is_storable = fields.Boolean(related='product_id.is_storable', string='Tracked in Inventory')
    state = fields.Selection(related='feeding_id.state')

    @api.depends_context('company')
    def _compute_product_domain(self):
        domain = self.env.company._zoo_feed_product_domain()
        for line in self:
            line.product_domain = domain

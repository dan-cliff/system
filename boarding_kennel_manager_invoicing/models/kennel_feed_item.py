from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tools import clean_context


class KennelFeedItem(models.Model):
    """One food item from inventory in a diet or an animal's stay, with how much and how often."""
    _name = 'kennel.feed.item'
    _description = 'Food Item'
    _order = 'sequence, id'
    _check_company_auto = True

    diet_id = fields.Many2one('kennel.diet', ondelete='cascade', index='btree_not_null')
    line_id = fields.Many2one('kennel.booking.line', string='Stay', ondelete='cascade', index='btree_not_null')
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one('res.company', compute='_compute_company_id', store=True, index=True)
    product_id = fields.Many2one(
        'product.product', string='Food', required=True, check_company=True, domain="product_domain",
    )
    product_domain = fields.Binary(compute='_compute_product_domain')
    quantity = fields.Float(string='Quantity per Feed', default=1.0, digits='Product Unit')
    uom_id = fields.Many2one(related='product_id.uom_id', string='Unit')
    frequency_id = fields.Many2one(
        'kennel.frequency', string='Frequency', required=True, check_company=True,
        default=lambda self: self.env.ref('boarding_kennel_manager.kennel_frequency_twice_daily', raise_if_not_found=False),
    )

    @api.depends('diet_id.company_id', 'line_id.company_id')
    def _compute_company_id(self):
        for item in self:
            item.company_id = item.line_id.company_id or item.diet_id.company_id

    @api.depends_context('company')
    @api.depends('company_id')
    def _compute_product_domain(self):
        for item in self:
            item.product_domain = (item.company_id or self.env.company)._kennel_food_domain()

    @api.constrains('diet_id', 'line_id')
    def _check_parent(self):
        for item in self:
            if bool(item.diet_id) == bool(item.line_id):
                raise ValidationError(self.env._('A food item belongs to either a diet or a stay.'))

    @api.constrains('quantity')
    def _check_quantity(self):
        for item in self:
            if item.quantity <= 0:
                raise ValidationError(self.env._('%s: enter how much to feed.', item.product_id.display_name))

    def _describe(self, with_frequency=True):
        """'Dry biscuits 0.25 kg (Twice a Day)'."""
        self.ensure_one()
        text = f'{self.product_id.display_name} {self.quantity:g} {self.uom_id.name or ""}'.strip()
        return f'{text} ({self.frequency_id.name})' if with_frequency and self.frequency_id else text

    def _copy_values(self):
        return [Command.create({
            'sequence': item.sequence, 'product_id': item.product_id.id,
            'quantity': item.quantity, 'frequency_id': item.frequency_id.id,
        }) for item in self]


class KennelDiet(models.Model):
    _inherit = 'kennel.diet'

    feed_item_ids = fields.One2many('kennel.feed.item', 'diet_id', string='Food', copy=True)


class KennelBookingLine(models.Model):
    _inherit = 'kennel.booking.line'

    feed_item_ids = fields.One2many('kennel.feed.item', 'line_id', string='Food', copy=True)
    feed_summary = fields.Char(string='Food Items', compute='_compute_feed_summary')

    @api.depends('feed_item_ids.product_id', 'feed_item_ids.quantity', 'feed_item_ids.frequency_id')
    def _compute_feed_summary(self):
        for line in self:
            line.feed_summary = ', '.join(item._describe() for item in line.feed_item_ids) or False

    def _uses_items(self):
        return self.use_feed_items and self.feed_item_ids

    def _feed_times(self):
        if not self._uses_items():
            return super()._feed_times()
        return sorted({slot for item in self.feed_item_ids for slot in item.frequency_id._get_times()})

    def _feed_description(self, slot=None):
        if not self.use_feed_items:
            return super()._feed_description(slot)
        items = self.feed_item_ids
        if slot:
            # The items due at this feed.
            items = items.filtered(lambda item: tuple(slot) in item.frequency_id._get_times())
        return '\n'.join(item._describe(with_frequency=not slot) for item in items)

    @api.onchange('diet_id')
    def _onchange_diet_feed_items(self):
        if self.use_feed_items and self.diet_id:
            self.feed_item_ids = [Command.clear()] + self.diet_id.feed_item_ids._copy_values()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line, vals in zip(lines, vals_list):
            if 'feed_item_ids' not in vals and line.use_feed_items and line.diet_id.feed_item_ids:
                line.feed_item_ids = line.diet_id.feed_item_ids._copy_values()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if 'diet_id' in vals and 'feed_item_ids' not in vals:
            for line in self.filtered('use_feed_items'):
                line.feed_item_ids = [Command.clear()] + line.diet_id.feed_item_ids._copy_values()
        if 'feed_item_ids' in vals or 'diet_id' in vals:
            # New feed times: swap the open feeds on the list for ones at the new times.
            self.task_ids.filtered(lambda task: task.task_type == 'feed' and task.state == 'todo').sudo().unlink()
            self.env['kennel.task']._generate_for_bookings(self.booking_id)
        return res


class KennelTask(models.Model):
    _inherit = 'kennel.task'

    @api.depends('line_id.feed_item_ids.quantity', 'line_id.feed_item_ids.product_id')
    def _compute_quantity_given(self):
        return super()._compute_quantity_given()


class KennelCustomDietWizard(models.TransientModel):
    _inherit = 'kennel.custom.diet.wizard'

    def action_create(self):
        # The dialog's context carries default_line_id, which mustn't reach the diet's food items.
        line = self.line_id.with_context(clean_context(self.env.context))
        items = line.feed_item_ids._copy_values() if line.use_feed_items else None
        res = super().action_create()
        if items is not None:
            # Saving the new diet on the line reloads its food from the (still empty) diet: fill both.
            line.diet_id.feed_item_ids = items
            line.feed_item_ids = [Command.clear()] + line.diet_id.feed_item_ids._copy_values()
        return res

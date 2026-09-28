from odoo import api, fields, models


def feed_items_enabled(company):
    """Food is picked from inventory (a table of food items) instead of typed in: the company integrates
    bookings with invoicing and the invoicing module, which provides the food items, is installed."""
    return bool(company.kennel_invoicing) and 'kennel.feed.item' in company.env


class KennelDiet(models.Model):
    _name = 'kennel.diet'
    _description = 'Diet'
    _order = 'resident_id desc, name'
    _check_company_auto = True

    name = fields.Char(required=True)
    species_id = fields.Many2one(
        'kennel.species', index=True, check_company=True,
        help='Species this diet is intended for. Leave empty for any species.',
    )
    resident_id = fields.Many2one(
        'kennel.resident', string='Custom Diet For', index=True, ondelete='cascade', check_company=True,
        help='Set for a custom diet made for one animal. Standard diets leave this empty.',
    )
    food = fields.Text(string='Food Required', help='What to feed and how much, e.g. "1 cup of adult dry biscuits".')
    use_feed_items = fields.Boolean(compute='_compute_use_feed_items')
    frequency_id = fields.Many2one(
        'kennel.frequency', string='Frequency', check_company=True,
        default=lambda self: self.env.ref('boarding_kennel_manager.kennel_frequency_twice_daily', raise_if_not_found=False),
    )
    owner_supplied_food = fields.Boolean(help='The owner brings the food for the stay.')
    instructions = fields.Text(string='Feeding Instructions')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', index=True, default=lambda self: self.env.company,
        help='Leave empty to share this diet with every company.',
    )

    @api.depends('company_id')
    @api.depends_context('company')
    def _compute_use_feed_items(self):
        for diet in self:
            diet.use_feed_items = feed_items_enabled(diet.company_id or self.env.company)

    def _feed_values(self):
        """Feed details a booking line copies from this diet."""
        self.ensure_one()
        return {
            'food': self.food,
            'frequency_id': self.frequency_id.id,
            'owner_supplied_food': self.owner_supplied_food,
            'feeding_instructions': self.instructions,
        }

from odoo import api, fields, models


class KennelCustomDietWizard(models.TransientModel):
    """Make a custom diet for one animal from its booking line, and use it for the stay."""
    _name = 'kennel.custom.diet.wizard'
    _description = 'Create Custom Diet'

    line_id = fields.Many2one('kennel.booking.line', required=True, ondelete='cascade')
    resident_id = fields.Many2one(related='line_id.resident_id')
    name = fields.Char(compute='_compute_from_line', store=True, readonly=False)
    food = fields.Char(compute='_compute_from_line', store=True, readonly=False)
    quantity = fields.Char(string='Quantity per Feed', compute='_compute_from_line', store=True, readonly=False)
    frequency_id = fields.Many2one('kennel.frequency', string='Frequency', compute='_compute_from_line',
                                   store=True, readonly=False)
    owner_supplied_food = fields.Boolean(compute='_compute_from_line', store=True, readonly=False)
    instructions = fields.Text(string='Feeding Instructions', compute='_compute_from_line', store=True, readonly=False)
    set_as_usual = fields.Boolean(
        string='Make it the Usual Diet', default=True,
        help='Pre-fill this diet on the animal\'s future bookings.',
    )

    @api.depends('line_id')
    def _compute_from_line(self):
        # Start from what the stay currently has.
        for wizard in self:
            line = wizard.line_id
            wizard.name = self.env._('%s - Custom Diet', line.resident_id.name)
            wizard.food = line.food
            wizard.quantity = line.quantity
            wizard.frequency_id = line.frequency_id
            wizard.owner_supplied_food = line.owner_supplied_food
            wizard.instructions = line.feeding_instructions

    def action_create(self):
        self.ensure_one()
        resident = self.line_id.resident_id
        diet = self.env['kennel.diet'].create({
            'name': self.name or self.env._('%s - Custom Diet', resident.name),
            'resident_id': resident.id,
            'species_id': resident.species_id.id,
            'company_id': resident.company_id.id,
            'food': self.food,
            'quantity': self.quantity,
            'frequency_id': self.frequency_id.id,
            'owner_supplied_food': self.owner_supplied_food,
            'instructions': self.instructions,
        })
        self.line_id.diet_id = diet
        if self.set_as_usual:
            resident.default_diet_id = diet
        return {'type': 'ir.actions.act_window_close'}

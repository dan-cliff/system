from odoo import api, fields, models
from odoo.exceptions import ValidationError


class KennelBookingLine(models.Model):
    """One animal's stay within a booking: its yard, diet and feed details."""
    _name = 'kennel.booking.line'
    _description = 'Booking Animal'
    _order = 'booking_id, sequence, id'
    _rec_name = 'resident_id'
    _check_company_auto = True

    booking_id = fields.Many2one('kennel.booking', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related='booking_id.company_id', store=True, index=True)
    partner_id = fields.Many2one(related='booking_id.partner_id', string='Customer', store=True)
    arrival_datetime = fields.Datetime(related='booking_id.arrival_datetime', string='Arrival', store=True)
    departure_datetime = fields.Datetime(related='booking_id.departure_datetime', string='Departure', store=True)
    state = fields.Selection(related='booking_id.state', store=True)
    resident_id = fields.Many2one(
        'kennel.resident', string='Animal', required=True, index=True, ondelete='restrict', check_company=True,
        domain="[('partner_id', '=', partner_id)]",
    )
    species_id = fields.Many2one(related='resident_id.species_id')
    yard_id = fields.Many2one(
        'kennel.yard', string='Yard', index=True, check_company=True,
        domain="['|', ('species_ids', '=', False), ('species_ids', 'in', species_id)]",
    )
    diet_id = fields.Many2one(
        'kennel.diet', string='Diet', check_company=True,
        compute='_compute_diet_id', store=True, readonly=False,
        domain="[('resident_id', 'in', [False, resident_id]), ('species_id', 'in', [False, species_id])]",
        help='Standard diets, and custom diets made for this animal. Picking one fills in the feed details.',
    )
    food = fields.Char(compute='_compute_feed', store=True, readonly=False)
    quantity = fields.Char(string='Quantity per Feed', compute='_compute_feed', store=True, readonly=False)
    frequency_id = fields.Many2one(
        'kennel.frequency', string='Frequency', check_company=True,
        compute='_compute_feed', store=True, readonly=False,
    )
    owner_supplied_food = fields.Boolean(compute='_compute_feed', store=True, readonly=False)
    feeding_instructions = fields.Text(compute='_compute_feed', store=True, readonly=False)
    medical_notes = fields.Text(
        string='Medical Care Requirements', compute='_compute_medical_notes', store=True, readonly=False,
        help='Conditions, allergies and care needed during this stay. Starts from the animal\'s medical notes.',
    )
    vaccination_expiry_date = fields.Date(related='resident_id.vaccination_expiry_date')
    vaccination_expired = fields.Boolean(
        compute='_compute_vaccination_expired',
        help='The animal\'s vaccinations run out before departure (or no date is recorded).',
    )

    task_ids = fields.One2many('kennel.task', 'line_id', string='Tasks')

    _resident_booking_uniq = models.Constraint(
        'UNIQUE (booking_id, resident_id)', 'An animal can only be on a booking once.',
    )

    @api.depends('resident_id')
    def _compute_diet_id(self):
        for line in self:
            line.diet_id = line.resident_id.default_diet_id

    # Only the diet itself: later edits to a diet mustn't rewrite past and current stays.
    @api.depends('diet_id')
    def _compute_feed(self):
        for line in self:
            values = line.diet_id._feed_values() if line.diet_id else dict.fromkeys(
                ('food', 'quantity', 'frequency_id', 'owner_supplied_food', 'feeding_instructions'), False,
            )
            line.update(values)

    @api.depends('resident_id')
    def _compute_medical_notes(self):
        for line in self:
            line.medical_notes = line.resident_id.medical_notes

    @api.depends('vaccination_expiry_date', 'departure_datetime')
    def _compute_vaccination_expired(self):
        for line in self:
            departure = line.departure_datetime and fields.Datetime.context_timestamp(
                line, line.departure_datetime).date()
            line.vaccination_expired = bool(line.resident_id) and bool(departure) and (
                not line.vaccination_expiry_date or line.vaccination_expiry_date < departure)

    def _overlapping_domain(self):
        self.ensure_one()
        return [
            ('id', '!=', self.id),
            ('state', '!=', 'cancelled'),
            ('arrival_datetime', '<', self.departure_datetime),
            ('departure_datetime', '>', self.arrival_datetime),
        ]

    @api.constrains('resident_id', 'arrival_datetime', 'departure_datetime', 'state')
    def _check_resident_overlap(self):
        for line in self.filtered(lambda line: line.state != 'cancelled'):
            clash = self.search(line._overlapping_domain() + [('resident_id', '=', line.resident_id.id)], limit=1)
            if clash:
                raise ValidationError(self.env._(
                    '%(animal)s is already booked in on %(booking)s at the same time.',
                    animal=line.resident_id.name, booking=clash.booking_id.name))

    @api.constrains('yard_id', 'arrival_datetime', 'departure_datetime', 'state')
    def _check_yard_capacity(self):
        for line in self.filtered(lambda line: line.yard_id.capacity and line.state != 'cancelled'):
            others = self.search(line._overlapping_domain() + [('yard_id', '=', line.yard_id.id)])
            stays = [(line.arrival_datetime, line.departure_datetime)] + [
                (other.arrival_datetime, other.departure_datetime) for other in others]
            # Occupancy only rises when someone arrives, so check it at each arrival during this stay.
            for moment in {max(start, line.arrival_datetime) for start, _end in stays}:
                present = sum(1 for start, end in stays if start <= moment < end)
                if present > line.yard_id.capacity:
                    raise ValidationError(self.env._(
                        '%(yard)s holds %(capacity)s animal(s) at a time, and is full for part of %(booking)s.',
                        yard=line.yard_id.display_name, capacity=line.yard_id.capacity,
                        booking=line.booking_id.name))

    @api.constrains('yard_id', 'resident_id')
    def _check_yard_species(self):
        for line in self:
            yard = line.yard_id
            if yard.species_ids and line.resident_id.species_id and line.resident_id.species_id not in yard.species_ids:
                raise ValidationError(self.env._(
                    '%(yard)s is not suitable for %(species)s (%(animal)s).',
                    yard=yard.display_name, species=line.resident_id.species_id.name, animal=line.resident_id.name))

    def write(self, vals):
        res = super().write(vals)
        if 'frequency_id' in vals:
            # New feed times: swap the open feeds on the list for ones at the new times.
            self.task_ids.filtered(lambda task: task.task_type == 'feed' and task.state == 'todo').sudo().unlink()
            self.env['kennel.task']._generate_for_bookings(self.booking_id)
        return res

    def action_custom_diet(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Custom Diet for %s', self.resident_id.name),
            'res_model': 'kennel.custom.diet.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_id': self.id},
        }

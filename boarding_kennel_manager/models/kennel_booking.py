from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command


class KennelBooking(models.Model):
    _name = 'kennel.booking'
    _description = 'Booking'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _order = 'arrival_datetime desc, id desc'
    _check_company_auto = True
    # Customers can post in the chatter from the portal.
    _mail_post_access = 'read'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True, index=True,
        default=lambda self: self.env._('New'),
    )
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, index=True, tracking=True, check_company=True,
    )
    arrival_datetime = fields.Datetime(string='Arrival', required=True, tracking=True)
    departure_datetime = fields.Datetime(string='Departure', required=True, tracking=True)
    nights = fields.Integer(compute='_compute_nights', store=True)
    resident_ids = fields.Many2many(
        'kennel.resident', string='Animals', check_company=True,
        domain="[('partner_id', '=', partner_id)]",
        help='Only the selected customer\'s residents are offered.',
    )
    line_ids = fields.One2many('kennel.booking.line', 'booking_id', string='Animal Details', copy=True)
    medication_ids = fields.One2many('kennel.medication', 'booking_id', string='Medication', copy=True)
    administration_ids = fields.One2many('kennel.medication.administration', 'booking_id', string='Medication Log')
    observation_ids = fields.One2many('kennel.observation', 'booking_id', string='Observations')
    task_ids = fields.One2many('kennel.task', 'booking_id', string='Daily Tasks')
    task_todo_count = fields.Integer(compute='_compute_task_todo_count')
    medication_count = fields.Integer(compute='_compute_counts')
    observation_count = fields.Integer(compute='_compute_counts')
    concern_count = fields.Integer(compute='_compute_counts')
    vaccination_warning = fields.Char(compute='_compute_vaccination_warning')
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('checked_in', 'Checked In'),
            ('checked_out', 'Checked Out'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft', required=True, tracking=True, copy=False,
    )
    checked_in_datetime = fields.Datetime(string='Checked In At', readonly=True, copy=False)
    checked_out_datetime = fields.Datetime(string='Checked Out At', readonly=True, copy=False)
    user_id = fields.Many2one('res.users', string='Booked By', default=lambda self: self.env.user, tracking=True)
    notes = fields.Html()
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)

    @api.depends('arrival_datetime', 'departure_datetime')
    def _compute_nights(self):
        for booking in self:
            if booking.arrival_datetime and booking.departure_datetime:
                arrival = fields.Datetime.context_timestamp(booking, booking.arrival_datetime).date()
                departure = fields.Datetime.context_timestamp(booking, booking.departure_datetime).date()
                booking.nights = max((departure - arrival).days, 0)
            else:
                booking.nights = 0

    @api.depends('medication_ids', 'observation_ids.concern')
    def _compute_counts(self):
        for booking in self:
            booking.medication_count = len(booking.medication_ids)
            booking.observation_count = len(booking.observation_ids)
            booking.concern_count = len(booking.observation_ids.filtered('concern'))

    @api.depends('task_ids.state')
    def _compute_task_todo_count(self):
        for booking in self:
            booking.task_todo_count = len(booking.task_ids.filtered(lambda task: task.state == 'todo'))

    def _compute_access_url(self):
        super()._compute_access_url()
        for booking in self:
            booking.access_url = f'/my/kennel/bookings/{booking.id}'

    @api.depends('line_ids.vaccination_expired', 'line_ids.resident_id')
    def _compute_vaccination_warning(self):
        for booking in self:
            names = booking.line_ids.filtered('vaccination_expired').resident_id.mapped('name')
            booking.vaccination_warning = self.env._(
                'Vaccinations run out before departure for: %s', ', '.join(names),
            ) if names else False

    @api.constrains('arrival_datetime', 'departure_datetime')
    def _check_dates(self):
        for booking in self:
            if booking.departure_datetime <= booking.arrival_datetime:
                raise ValidationError(self.env._('%s: departure must be after arrival.', booking.display_name))

    @api.constrains('partner_id', 'resident_ids')
    def _check_residents_customer(self):
        for booking in self:
            others = booking.resident_ids.filtered(lambda r: r.partner_id != booking.partner_id)
            if others:
                raise ValidationError(self.env._(
                    '%(booking)s: %(animals)s belong to another customer, not %(customer)s.',
                    booking=booking.display_name, animals=', '.join(others.mapped('name')),
                    customer=booking.partner_id.display_name))

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        self.resident_ids = self.resident_ids.filtered(lambda r: r.partner_id == self.partner_id)

    @api.onchange('resident_ids')
    def _onchange_resident_ids(self):
        """Give each selected animal its own line, and drop the lines of animals taken off."""
        residents = self.resident_ids._origin
        lines = self.line_ids.filtered(lambda line: line.resident_id._origin in residents)
        for resident in residents - lines.resident_id._origin:
            lines |= lines.new({'resident_id': resident.id})
        self.line_ids = lines

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', self.env._('New')) == self.env._('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('kennel.booking') or self.env._('New')
        bookings = super().create(vals_list)
        bookings._sync_lines()
        bookings._subscribe_customer()
        return bookings

    def write(self, vals):
        res = super().write(vals)
        if 'partner_id' in vals:
            self._subscribe_customer()
        if 'resident_ids' in vals:
            self._sync_lines()
        elif 'line_ids' in vals:
            # Lines edited on their own (e.g. one deleted): the animals follow the lines.
            for booking in self:
                if booking.resident_ids != booking.line_ids.resident_id:
                    super(KennelBooking, booking).write({'resident_ids': [Command.set(booking.line_ids.resident_id.ids)]})
        return res

    def _sync_lines(self):
        """One line per selected animal: add lines for new animals, drop those of animals taken off."""
        for booking in self:
            lines = booking.line_ids
            commands = [Command.create({'resident_id': resident.id})
                        for resident in booking.resident_ids - lines.resident_id]
            commands += [Command.unlink(line.id)
                         for line in lines.filtered(lambda line: line.resident_id not in booking.resident_ids)]
            if commands:
                super(KennelBooking, booking).write({'line_ids': commands})

    def _subscribe_customer(self):
        """The customer follows the booking, so they hear about keepers' messages (by email and in the portal)."""
        for booking in self:
            booking.message_subscribe(partner_ids=booking.partner_id.ids)

    def action_confirm(self):
        self._check_has_animals()
        self.write({'state': 'confirmed'})

    def action_check_in(self):
        self._check_has_animals()
        self.write({'state': 'checked_in', 'checked_in_datetime': fields.Datetime.now()})
        self.env['kennel.task']._generate_for_bookings(self)

    def action_check_out(self):
        self.write({'state': 'checked_out', 'checked_out_datetime': fields.Datetime.now()})
        self._cancel_open_tasks()

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        self._cancel_open_tasks()

    def action_draft(self):
        self.write({'state': 'draft', 'checked_in_datetime': False, 'checked_out_datetime': False})
        self._cancel_open_tasks()

    def _cancel_open_tasks(self):
        self.task_ids.filtered(lambda task: task.state == 'todo').write({'state': 'cancelled'})

    def action_view_tasks(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('boarding_kennel_manager.kennel_task_action_all')
        action['domain'] = [('booking_id', '=', self.id)]
        action['context'] = {'search_default_filter_todo': 1}
        return action

    def action_portal_preview(self):
        """Open the customer's portal page for this record."""
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.get_portal_url(), 'target': 'self'}

    def action_portal_invite(self):
        return self.partner_id.action_kennel_portal_invite()

    def _check_has_animals(self):
        for booking in self:
            if not booking.resident_ids:
                raise UserError(self.env._('%s: add the animals being booked in first.', booking.display_name))

    def action_view_medication_log(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Medication Log'),
            'res_model': 'kennel.medication.administration',
            'view_mode': 'list,form',
            'domain': [('booking_id', '=', self.id)],
            'context': {'default_booking_id': self.id},
        }

    def action_view_observations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Observations'),
            'res_model': 'kennel.observation',
            'view_mode': 'list,form',
            'domain': [('booking_id', '=', self.id)],
            'context': {'default_booking_id': self.id},
        }

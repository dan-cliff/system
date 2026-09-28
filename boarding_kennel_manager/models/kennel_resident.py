from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class KennelResident(models.Model):
    _name = 'kennel.resident'
    _description = 'Resident'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'image.mixin']
    _order = 'name, id'
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, index=True, tracking=True, check_company=True,
    )
    species_id = fields.Many2one('kennel.species', string='Species', tracking=True, check_company=True)
    breed = fields.Char(tracking=True)
    sex_id = fields.Many2one('kennel.sex', string='Sex', tracking=True, check_company=True)
    desexed = fields.Boolean(tracking=True)
    date_of_birth = fields.Date(tracking=True)
    age = fields.Char(compute='_compute_age')
    colour = fields.Char(string='Colour / Markings')
    microchip = fields.Char(string='Microchip Number', tracking=True)
    weight = fields.Float(string='Weight (kg)', digits=(6, 2), tracking=True)
    vet_id = fields.Many2one(
        'res.partner', string='Veterinarian', check_company=True,
        help='The animal\'s regular vet clinic.',
    )
    vaccination_expiry_date = fields.Date(
        string='Vaccinations Due', tracking=True,
        help='When the current vaccinations run out. Bookings warn when this is before departure.',
    )
    default_diet_id = fields.Many2one(
        'kennel.diet', string='Usual Diet', tracking=True, check_company=True,
        domain="[('resident_id', 'in', [False, id]), ('species_id', 'in', [False, species_id])]",
        help='Pre-filled on this animal\'s bookings.',
    )
    custom_diet_ids = fields.One2many('kennel.diet', 'resident_id', string='Custom Diets')
    medical_notes = fields.Text(
        help='Standing conditions, allergies and medical needs. Copied onto each new booking.',
    )
    behaviour_notes = fields.Text(help='Temperament, handling and compatibility with other animals.')
    notes = fields.Html()
    booking_line_ids = fields.One2many('kennel.booking.line', 'resident_id', string='Stays')
    booking_count = fields.Integer(compute='_compute_booking_count')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)

    @api.depends('date_of_birth')
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for resident in self:
            if not resident.date_of_birth:
                resident.age = False
                continue
            delta = relativedelta(today, resident.date_of_birth)
            if delta.years:
                resident.age = self.env._('%(years)s y %(months)s m', years=delta.years, months=delta.months)
            elif delta.months:
                resident.age = self.env._('%(months)s m', months=delta.months)
            else:
                resident.age = self.env._('%(days)s d', days=max(delta.days, 0))

    @api.depends('booking_line_ids.booking_id')
    def _compute_booking_count(self):
        for resident in self:
            resident.booking_count = len(resident.booking_line_ids.booking_id)

    @api.depends('name', 'partner_id')
    @api.depends_context('show_customer')
    def _compute_display_name(self):
        for resident in self:
            if self.env.context.get('show_customer') and resident.partner_id:
                resident.display_name = f'{resident.name} ({resident.partner_id.name})'
            else:
                resident.display_name = resident.name

    def action_view_bookings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Bookings'),
            'res_model': 'kennel.booking',
            'view_mode': 'list,calendar,form',
            'domain': [('resident_ids', 'in', self.ids)],
            'context': {'default_partner_id': self.partner_id.id, 'default_resident_ids': self.ids},
        }

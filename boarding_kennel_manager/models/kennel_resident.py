from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class KennelResident(models.Model):
    _name = 'kennel.resident'
    _description = 'Resident'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin', 'image.mixin']
    _order = 'name, id'
    _check_company_auto = True
    # Customers can post in the chatter from the portal.
    _mail_post_access = 'read'

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
    task_ids = fields.One2many('kennel.task', 'resident_id', string='Care Log')
    care_count = fields.Integer(compute='_compute_care_count')
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

    @api.depends('task_ids.state')
    def _compute_care_count(self):
        for resident in self:
            resident.care_count = len(resident.task_ids.filtered(lambda task: task.state == 'done'))

    def _compute_access_url(self):
        super()._compute_access_url()
        for resident in self:
            resident.access_url = f'/my/kennel/animals/{resident.id}'

    @api.model_create_multi
    def create(self, vals_list):
        residents = super().create(vals_list)
        residents._subscribe_customer()
        return residents

    def write(self, vals):
        res = super().write(vals)
        if 'partner_id' in vals:
            self._subscribe_customer()
        return res

    def _subscribe_customer(self):
        """The customer follows their animal, so they hear about keepers' messages (by email and in the portal)."""
        for resident in self:
            resident.message_subscribe(partner_ids=resident.partner_id.ids)

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

    def action_view_care_log(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('boarding_kennel_manager.kennel_task_action_all')
        action['name'] = self.env._('Care Log: %s', self.name)
        action['domain'] = [('resident_id', '=', self.id)]
        action['context'] = {'search_default_filter_done': 1}
        return action

    def action_portal_preview(self):
        """Open the customer's portal page for this record."""
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.get_portal_url(), 'target': 'self'}

    def action_portal_invite(self):
        return self.partner_id.action_kennel_portal_invite()

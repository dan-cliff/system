from odoo import api, fields, models
from odoo.exceptions import ValidationError


class KennelMedication(models.Model):
    """Medication to give an animal during its stay."""
    _name = 'kennel.medication'
    _description = 'Medication'
    _order = 'booking_id, resident_id, id'
    _check_company_auto = True

    booking_id = fields.Many2one('kennel.booking', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='booking_id.company_id', store=True, index=True)
    resident_id = fields.Many2one(
        'kennel.resident', string='Animal', required=True, index=True, ondelete='restrict', check_company=True,
    )
    name = fields.Char(string='Medication', required=True)
    dose = fields.Char(help='Amount per dose, e.g. "1 tablet" or "0.5 ml".')
    route_id = fields.Many2one('kennel.medication.route', string='Route', check_company=True)
    frequency_id = fields.Many2one('kennel.frequency', string='Frequency', check_company=True)
    times = fields.Char(string='When', help='Times of day or with meals, e.g. "8am and 6pm with food".')
    start_date = fields.Date(help='First day to give it. Leave empty to start on arrival.')
    end_date = fields.Date(help='Last day to give it. Leave empty to continue until departure.')
    instructions = fields.Text()
    administration_ids = fields.One2many('kennel.medication.administration', 'medication_id', string='Doses')
    last_given_datetime = fields.Datetime(string='Last Given', compute='_compute_last_given')

    task_ids = fields.One2many('kennel.task', 'medication_id', string='Tasks')

    @api.model_create_multi
    def create(self, vals_list):
        medications = super().create(vals_list)
        self.env['kennel.task']._generate_for_bookings(medications.booking_id)
        return medications

    def write(self, vals):
        res = super().write(vals)
        if {'frequency_id', 'start_date', 'end_date', 'resident_id'} & set(vals):
            # Drop open doses that no longer apply, then re-add today's from the new schedule.
            self.task_ids.filtered(lambda task: task.state == 'todo').sudo().unlink()
            self.env['kennel.task']._generate_for_bookings(self.booking_id)
        return res

    @api.depends('administration_ids.administered_datetime', 'administration_ids.outcome_id.problem')
    def _compute_last_given(self):
        for medication in self:
            given = medication.administration_ids.filtered(lambda dose: not dose.outcome_id.problem)
            medication.last_given_datetime = max(given.mapped('administered_datetime'), default=False)

    @api.depends('name', 'resident_id', 'dose')
    def _compute_display_name(self):
        for medication in self:
            parts = [medication.resident_id.name, medication.name, medication.dose]
            medication.display_name = ' - '.join(part for part in parts if part)

    @api.constrains('resident_id', 'booking_id')
    def _check_resident_on_booking(self):
        for medication in self:
            if medication.resident_id not in medication.booking_id.resident_ids:
                raise ValidationError(self.env._(
                    '%(animal)s is not on booking %(booking)s.',
                    animal=medication.resident_id.name, booking=medication.booking_id.name))

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for medication in self:
            if medication.start_date and medication.end_date and medication.end_date < medication.start_date:
                raise ValidationError(self.env._('%s: the end date is before the start date.', medication.display_name))

    def action_record_dose(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Record Dose'),
            'res_model': 'kennel.medication.administration',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_booking_id': self.booking_id.id,
                'default_medication_id': self.id,
                'default_dose_given': self.dose,
            },
        }


class KennelMedicationAdministration(models.Model):
    """A dose given (or missed) - the medication log."""
    _name = 'kennel.medication.administration'
    _description = 'Medication Dose'
    _order = 'administered_datetime desc, id desc'
    _rec_name = 'medication_id'
    _check_company_auto = True

    booking_id = fields.Many2one('kennel.booking', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='booking_id.company_id', store=True, index=True)
    medication_id = fields.Many2one(
        'kennel.medication', string='Medication', required=True, ondelete='cascade', index=True,
        check_company=True, domain="[('booking_id', '=', booking_id)]",
    )
    resident_id = fields.Many2one(related='medication_id.resident_id', string='Animal', store=True)
    administered_datetime = fields.Datetime(string='Date / Time', required=True, default=fields.Datetime.now)
    dose_given = fields.Char()
    outcome_id = fields.Many2one(
        'kennel.dose.outcome', string='Outcome', required=True, check_company=True,
        default=lambda self: self.env.ref('boarding_kennel_manager.kennel_dose_outcome_given', raise_if_not_found=False),
    )
    problem = fields.Boolean(related='outcome_id.problem', store=True, string='Needs Attention')
    user_id = fields.Many2one('res.users', string='Given By', required=True, default=lambda self: self.env.user)
    notes = fields.Text()

    @api.constrains('booking_id', 'medication_id')
    def _check_booking(self):
        for dose in self:
            if dose.medication_id.booking_id != dose.booking_id:
                raise ValidationError(self.env._(
                    '%(medication)s is not on booking %(booking)s.',
                    medication=dose.medication_id.display_name, booking=dose.booking_id.name))

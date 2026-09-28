from odoo import api, fields, models
from odoo.exceptions import ValidationError


class KennelObservation(models.Model):
    """A keeper's note on an animal during its stay."""
    _name = 'kennel.observation'
    _description = 'Keeper Observation'
    _inherit = ['mail.activity.mixin']
    _order = 'observation_datetime desc, id desc'
    _rec_name = 'summary'
    _check_company_auto = True

    booking_id = fields.Many2one('kennel.booking', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='booking_id.company_id', store=True, index=True)
    resident_id = fields.Many2one(
        'kennel.resident', string='Animal', required=True, index=True, ondelete='restrict', check_company=True,
    )
    observation_datetime = fields.Datetime(string='Date / Time', required=True, default=fields.Datetime.now)
    type_id = fields.Many2one(
        'kennel.observation.type', string='Type', check_company=True,
        default=lambda self: self.env.ref('boarding_kennel_manager.kennel_observation_type_general', raise_if_not_found=False),
    )
    summary = fields.Char(required=True)
    details = fields.Text()
    concern = fields.Boolean(
        compute='_compute_concern', store=True, readonly=False,
        help='Needs follow-up, e.g. a vet visit or letting the owner know.',
    )
    user_id = fields.Many2one('res.users', string='Keeper', required=True, default=lambda self: self.env.user)

    @api.depends('type_id')
    def _compute_concern(self):
        for observation in self:
            observation.concern = observation.type_id.concern

    @api.constrains('resident_id', 'booking_id')
    def _check_resident_on_booking(self):
        for observation in self:
            if observation.resident_id not in observation.booking_id.resident_ids:
                raise ValidationError(self.env._(
                    '%(animal)s is not on booking %(booking)s.',
                    animal=observation.resident_id.name, booking=observation.booking_id.name))

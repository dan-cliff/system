from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ZooEnclosure(models.Model):
    _name = 'zoo.enclosure'
    _description = 'Enclosure'
    _inherit = ['mail.thread']
    _order = 'name'
    _parent_store = True

    name = fields.Char(required=True, tracking=True)
    code = fields.Char()
    enclosure_type_id = fields.Many2one('zoo.enclosure.type', string='Type', tracking=True)
    facility_id = fields.Many2one(
        'zoo.facility', index=True, tracking=True,
        compute='_compute_facility_id', store=True, readonly=False,
    )
    location_id = fields.Many2one(
        'zoo.location', index=True, tracking=True,
        domain="[('facility_id', '=', facility_id)] if facility_id else []",
        help='Location within the facility.',
    )
    parent_id = fields.Many2one(
        'zoo.enclosure', string='Parent Enclosure', index=True, tracking=True, ondelete='restrict',
        domain="[('id', '!=', id)]",
        help='Group enclosures under a parent, e.g. to act on all of them at once.',
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('zoo.enclosure', 'parent_id', string='Sub-enclosures')
    child_count = fields.Integer(compute='_compute_child_count')
    capacity = fields.Integer(help='Maximum number of animals. Leave at 0 for no limit.', tracking=True)
    area = fields.Float(string='Area (m²)')
    description = fields.Html()

    # Environmental options
    climate_control_ids = fields.Many2many(
        'zoo.climate.control.type', string='Climate Controlled',
        help='How the climate in this enclosure is controlled.',
    )
    water_source_ids = fields.Many2many(
        'zoo.water.source.type', string='Water Source',
        help='Where the water in this enclosure comes from.',
    )
    central_monitoring = fields.Boolean(tracking=True, help='Monitored from the central monitoring system.')
    livestream = fields.Boolean(tracking=True, help='Has a livestream camera.')
    livestream_url = fields.Char(string='Livestream URL', tracking=True, help='Link to the livestream.')
    electric_fencing = fields.Boolean(tracking=True)
    observation_space = fields.Boolean(tracking=True, help='Has a space for visitors or staff to observe the animals.')
    animal_ids = fields.One2many('zoo.animal', 'enclosure_id', string='Animals')
    animal_count = fields.Integer(compute='_compute_animal_count', store=True)
    over_capacity = fields.Boolean(compute='_compute_animal_count', store=True)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint('UNIQUE (code)', 'An enclosure with this code already exists.')

    @api.depends('animal_ids', 'capacity')
    def _compute_animal_count(self):
        for enclosure in self:
            enclosure.animal_count = len(enclosure.animal_ids)
            enclosure.over_capacity = bool(enclosure.capacity) and enclosure.animal_count > enclosure.capacity

    @api.constrains('livestream', 'livestream_url')
    def _check_livestream_url(self):
        for enclosure in self:
            if enclosure.livestream and not (enclosure.livestream_url or '').strip():
                raise ValidationError(self.env._('%s: enter the Livestream URL.', enclosure.display_name))

    @api.depends('child_ids')
    def _compute_child_count(self):
        for enclosure in self:
            enclosure.child_count = len(enclosure.child_ids)

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if self._has_cycle():
            raise ValidationError(self.env._('An enclosure cannot be inside one of its own sub-enclosures.'))

    def action_view_children(self):
        """All enclosures under this one, at any depth, ready for bulk actions."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Sub-enclosures of %s', self.display_name),
            'res_model': 'zoo.enclosure',
            'view_mode': 'list,form',
            'domain': [('id', 'child_of', self.id), ('id', '!=', self.id)],
            'context': {'default_parent_id': self.id},
        }

    @api.depends('location_id.facility_id')
    def _compute_facility_id(self):
        for enclosure in self:
            enclosure.facility_id = enclosure.location_id.facility_id or enclosure.facility_id

    @api.onchange('facility_id')
    def _onchange_facility_id(self):
        if self.location_id.facility_id != self.facility_id:
            self.location_id = False

    @api.constrains('facility_id', 'location_id')
    def _check_location_facility(self):
        for enclosure in self:
            if enclosure.location_id and enclosure.location_id.facility_id != enclosure.facility_id:
                raise ValidationError(self.env._(
                    '%(enclosure)s: location %(location)s belongs to %(facility)s, not the enclosure\'s facility.',
                    enclosure=enclosure.display_name, location=enclosure.location_id.name,
                    facility=enclosure.location_id.facility_id.name))

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for enclosure in self:
            enclosure.display_name = f'[{enclosure.code}] {enclosure.name}' if enclosure.code else enclosure.name

    def action_view_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Moves'),
            'res_model': 'zoo.animal.move',
            'view_mode': 'list,form',
            'domain': ['|', ('from_enclosure_id', '=', self.id), ('to_enclosure_id', '=', self.id)],
        }

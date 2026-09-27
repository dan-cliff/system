from odoo import api, fields, models


class ZooEnclosure(models.Model):
    _name = 'zoo.enclosure'
    _description = 'Enclosure'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char()
    enclosure_type = fields.Selection(
        [
            ('paddock', 'Paddock'),
            ('pen', 'Pen'),
            ('aviary', 'Aviary'),
            ('house', 'Animal House'),
            ('vivarium', 'Vivarium'),
            ('aquarium', 'Aquarium'),
            ('pond', 'Pond'),
            ('quarantine', 'Quarantine'),
            ('other', 'Other'),
        ],
        string='Type',
        tracking=True,
    )
    capacity = fields.Integer(help='Maximum number of animals. Leave at 0 for no limit.', tracking=True)
    area = fields.Float(string='Area (m²)')
    description = fields.Html()
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

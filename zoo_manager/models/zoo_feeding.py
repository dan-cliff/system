from odoo import api, fields, models


class ZooFeeding(models.Model):
    _name = 'zoo.feeding'
    _description = 'Feeding Round'
    _inherit = ['mail.thread']
    _order = 'scheduled_datetime desc, id desc'

    enclosure_id = fields.Many2one('zoo.enclosure', required=True, index=True, tracking=True)
    animal_ids = fields.Many2many(
        'zoo.animal', 'zoo_animal_feeding_rel', 'feeding_id', 'animal_id', string='Animals',
        compute='_compute_animal_ids', store=True, readonly=False,
        domain="[('enclosure_id', '=', enclosure_id), ('state', '=', 'present')]",
    )
    scheduled_datetime = fields.Datetime(string='Scheduled', required=True, default=fields.Datetime.now)
    fed_datetime = fields.Datetime(string='Fed At', readonly=True, copy=False)
    user_id = fields.Many2one('res.users', string='Keeper', default=lambda self: self.env.user, tracking=True)
    food_given = fields.Text(help='What was given, if different from the animals\' diets.')
    consumption = fields.Selection(
        [
            ('all', 'All Eaten'),
            ('most', 'Mostly Eaten'),
            ('some', 'Partly Eaten'),
            ('none', 'Refused'),
        ],
        tracking=True,
    )
    notes = fields.Text()
    state = fields.Selection(
        [('planned', 'Planned'), ('done', 'Fed'), ('cancelled', 'Cancelled')],
        default='planned', required=True, tracking=True, copy=False,
    )

    @api.depends('enclosure_id')
    def _compute_animal_ids(self):
        for feeding in self:
            feeding.animal_ids = feeding.enclosure_id.animal_ids.filtered(lambda a: a.state == 'present')

    @api.depends('enclosure_id', 'scheduled_datetime')
    def _compute_display_name(self):
        for feeding in self:
            when = fields.Datetime.context_timestamp(feeding, feeding.scheduled_datetime).strftime('%Y-%m-%d %H:%M') if feeding.scheduled_datetime else ''
            feeding.display_name = f'{feeding.enclosure_id.display_name or ""} {when}'.strip()

    def action_mark_fed(self):
        self.write({'state': 'done', 'fed_datetime': fields.Datetime.now(), 'user_id': self.env.user.id})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_to_planned(self):
        self.write({'state': 'planned', 'fed_datetime': False})

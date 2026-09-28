from odoo import api, fields, models


class KennelYard(models.Model):
    _name = 'kennel.yard'
    _description = 'Yard'
    _inherit = ['mail.thread']
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(tracking=True)
    sequence = fields.Integer(default=10)
    yard_type_id = fields.Many2one('kennel.yard.type', string='Type', tracking=True, check_company=True)
    species_ids = fields.Many2many(
        'kennel.species', string='Suitable For', check_company=True,
        help='Species this yard can take. Leave empty for any species.',
    )
    feature_ids = fields.Many2many('kennel.yard.feature', string='Features', check_company=True)
    capacity = fields.Integer(
        tracking=True, default=1,
        help='Most animals the yard can hold at once. Leave at 0 for no limit.',
    )
    area = fields.Float(string='Area (m²)')
    description = fields.Html()
    line_ids = fields.One2many('kennel.booking.line', 'yard_id', string='Stays')
    occupant_count = fields.Integer(
        string='Checked In', compute='_compute_occupant_count',
        help='Animals checked in to this yard right now.',
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)

    _code_company_uniq = models.Constraint('UNIQUE (code, company_id)', 'A yard with this code already exists.')

    @api.depends('line_ids.booking_id.state')
    def _compute_occupant_count(self):
        counts = dict(self.env['kennel.booking.line']._read_group(
            [('yard_id', 'in', self.ids), ('booking_id.state', '=', 'checked_in')],
            ['yard_id'], ['__count'],
        ))
        for yard in self:
            yard.occupant_count = counts.get(yard._origin, 0)

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for yard in self:
            yard.display_name = f'[{yard.code}] {yard.name}' if yard.code else yard.name

    def action_open_control_plane(self):
        """The yard's full-screen enclosure display, in a new tab (it can be installed as an app from there)."""
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': f'/kennel/control-plane/{self.id}', 'target': 'new'}

    def action_view_stays(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Stays in %s', self.display_name),
            'res_model': 'kennel.booking.line',
            'view_mode': 'list,form',
            'domain': [('yard_id', '=', self.id)],
            'context': {'search_default_filter_current': 1},
        }

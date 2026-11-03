from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    action_ids = fields.One2many('advanced.action', 'production_id', string='Actions')
    action_open_count = fields.Integer(compute='_compute_action_open_count')

    def _compute_action_open_count(self):
        counts = dict(self.env['advanced.action'].sudo()._read_group(
            [('production_id', 'in', self.ids), ('state', 'in', ('open', 'in_progress'))],
            ['production_id'], ['__count']))
        for record in self:
            record.action_open_count = counts.get(record, 0)

    def action_open_actions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Actions'),
            'res_model': 'advanced.action',
            'view_mode': 'list,kanban,form',
            'domain': [('production_id', '=', self.id)],
            'context': {'default_production_id': self.id, 'default_source_app': 'manufacturing',
                        'search_default_open': 1},
        }

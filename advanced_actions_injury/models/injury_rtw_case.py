from odoo import fields, models


class InjuryRtwCase(models.Model):
    _inherit = 'injury.rtw.case'

    action_ids = fields.One2many('advanced.action', 'injury_case_id', string='Actions')
    action_open_count = fields.Integer(compute='_compute_action_open_count')

    def _compute_action_open_count(self):
        for record in self:
            record.action_open_count = len(
                record.action_ids.filtered(lambda action: action.state in ('open', 'in_progress'))
            )

    def action_open_actions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Actions'),
            'res_model': 'advanced.action',
            'view_mode': 'list,kanban,form',
            'domain': [('injury_case_id', '=', self.id)],
            'context': {'default_injury_case_id': self.id, 'search_default_open': 1},
        }

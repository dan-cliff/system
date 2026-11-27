from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    followup_action_ids = fields.One2many('advanced.action', 'followup_partner_id', string='Follow-up Actions')
    followup_action_open_count = fields.Integer(compute='_compute_followup_action_open_count')

    def _compute_followup_action_open_count(self):
        counts = dict(self.env['advanced.action']._read_group(
            [('followup_partner_id', 'in', self.ids), ('state', 'in', ('open', 'in_progress'))],
            ['followup_partner_id'], ['__count'],
        ))
        for partner in self:
            partner.followup_action_open_count = counts.get(partner, 0)

    def _followup_raise_action(self, summary, note, user, date=None, merge=False):
        self.ensure_one()
        return self.env['advanced.action']._accounting_raise(
            'followup_partner_id', self, summary, note, user, date=date, merge=merge)

    @api.model
    def _followup_partners_with_actions(self):
        actions = self.env['advanced.action'].sudo().search([
            ('followup_partner_id', '!=', False), ('state', 'in', ('open', 'in_progress')),
        ])
        return super()._followup_partners_with_actions() | actions.followup_partner_id

    def _followup_actions_done(self, feedback):
        super()._followup_actions_done(feedback)
        self.env['advanced.action']._accounting_done('followup_partner_id', self, feedback)

    def action_open_followup_actions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Follow-up Actions'),
            'res_model': 'advanced.action',
            'view_mode': 'list,kanban,form',
            'domain': [('followup_partner_id', '=', self.id)],
            'context': {'default_followup_partner_id': self.id, 'default_source_app': 'accounting',
                        'search_default_open': 1},
        }

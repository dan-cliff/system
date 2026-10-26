from datetime import timedelta

from odoo import api, fields, models
from odoo.tools import plaintext2html


class IncidentReport(models.Model):
    _inherit = 'incident.report'

    corrective_action_ids = fields.One2many('advanced.action', 'incident_id', string='Corrective Actions')

    @api.depends('corrective_action_ids.state')
    def _compute_corrective_actions_complete(self):
        # Cancelled actions don't hold up closing the incident.
        for rec in self:
            actions = rec.corrective_action_ids
            rec.corrective_actions_complete = bool(actions) and all(
                a.state in ('done', 'cancelled') for a in actions)

    def action_open_corrective_actions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Corrective Actions'),
            'res_model': 'advanced.action',
            'view_mode': 'list,kanban,form',
            'views': [
                (self.env.ref('advanced_actions_incident.view_advanced_action_list_incident').id, 'list'),
                (False, 'kanban'), (False, 'form'),
            ],
            'domain': [('incident_id', '=', self.id)],
            'context': {'default_incident_id': self.id},
        }

    def _create_corrective_actions(self, recommendations):
        today = fields.Date.today()
        responsible = self.responsible_manager_id or self.env.user
        Action = self.env['advanced.action']
        created = Action
        for rec in recommendations:
            control_type = self.env.ref(
                f"advanced_actions_incident.control_type_{rec['action_type']}", raise_if_not_found=False,
            )
            notes = f"[AI Generated]\n{rec['rationale']}" if rec['rationale'] else '[AI Generated]'
            created |= Action.create({
                'incident_id': self.id,
                'name': rec['name'],
                'control_type_id': control_type.id if control_type else False,
                'priority': rec['priority'],
                'user_ids': [(6, 0, responsible.ids)],
                'date_deadline': Action._date_to_deadline(today + timedelta(days=rec['days']), responsible),
                'description': plaintext2html(notes),
                'state': 'open',
            })
        return created

from odoo import api, fields, models


class IncidentReport(models.Model):
    """Extend incident.report with Emergency Broadcast integration."""

    _inherit = 'incident.report'

    emergency_broadcast_ids = fields.One2many(
        comodel_name='emergency.broadcast',
        inverse_name='incident_id',
        string='Emergency Broadcasts',
    )
    emergency_broadcast_count = fields.Integer(
        string='Emergency Broadcasts',
        compute='_compute_emergency_broadcast_count',
    )

    @api.depends('emergency_broadcast_ids')
    def _compute_emergency_broadcast_count(self):
        for record in self:
            record.emergency_broadcast_count = len(record.emergency_broadcast_ids)

    def action_view_emergency_broadcasts(self):
        """Open Emergency Broadcasts linked to this incident.

        Opens the form directly when there is exactly one record, otherwise
        opens the list view filtered to this incident so the user can create
        new ones with ``incident_id`` pre-filled.
        """
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Emergency Broadcasts',
            'res_model': 'emergency.broadcast',
            'domain': [('incident_id', '=', self.id)],
            'context': {'default_incident_id': self.id},
        }
        if self.emergency_broadcast_count == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.emergency_broadcast_ids[0].id
        else:
            action['view_mode'] = 'list,form'
        return action

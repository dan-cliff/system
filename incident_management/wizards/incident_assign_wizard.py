# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class IncidentAssignWizard(models.TransientModel):
    """Wizard for assigning a Responsible Manager to an incident report."""
    _name = 'incident.assign.wizard'
    _description = 'Assign Responsible Manager'

    incident_id = fields.Many2one(
        'incident.report', string='Incident', required=True, readonly=True)
    incident_name = fields.Char(related='incident_id.name', string='Reference')
    incident_type_ids = fields.Many2many(
        related='incident_id.incident_type_ids', string='Categories')

    responsible_manager_id = fields.Many2one(
        'res.users', string='Responsible Manager',
        required=True, domain=[('share', '=', False)])
    note = fields.Text(
        'Note to Manager',
        help='This note will be included in the notification sent to the manager.')
    notify_by_email = fields.Boolean('Notify Manager by Email', default=True)

    def action_assign(self):
        self.ensure_one()
        incident = self.incident_id
        if incident.state not in ('submitted', 'assigned'):
            raise UserError(_('This incident cannot be (re-)assigned in its current state.'))

        incident.write({
            'responsible_manager_id': self.responsible_manager_id.id,
            'state': 'assigned',
            'date_assigned': fields.Datetime.now(),
            'assignment_note': self.note,
        })

        partner_ids = (
            self.responsible_manager_id.partner_id.ids
            if self.notify_by_email else []
        )
        body = _(
            'Incident <strong>%(ref)s</strong> has been assigned to '
            '<strong>%(manager)s</strong> for investigation.',
            ref=incident.name,
            manager=self.responsible_manager_id.name,
        )
        if self.note:
            body += '<br/><br/><em>Note: %s</em>' % self.note

        incident.message_post(
            body=body,
            partner_ids=partner_ids,
            subtype_xmlid='mail.mt_note',
        )
        return {'type': 'ir.actions.act_window_close'}

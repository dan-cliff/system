# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class IncidentConfidentialWizard(models.TransientModel):
    """
    Wizard to manage the list of users authorised to view a
    confidential incident report.
    """
    _name = 'incident.confidential.wizard'
    _description = 'Manage Incident Confidential Access'

    incident_id = fields.Many2one(
        'incident.report', string='Incident',
        required=True, ondelete='cascade', readonly=True)
    incident_name = fields.Char(
        related='incident_id.name', string='Incident Reference', readonly=True)
    user_ids = fields.Many2many(
        'res.users',
        'incident_confidential_wizard_user_rel',
        'wizard_id', 'user_id',
        string='Authorised Users',
        domain=[('share', '=', False)],
        help='Internal users who may view this confidential incident report. '
             'The original reporter and the responsible manager always have '
             'access regardless of this list.')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        incident_id = self.env.context.get('default_incident_id')
        if incident_id:
            incident = self.env['incident.report'].browse(incident_id)
            res.setdefault('incident_id', incident_id)
            res.setdefault('user_ids', [(6, 0, incident.confidential_user_ids.ids)])
        return res

    def action_save(self):
        """Persist the updated user list back to the incident record."""
        self.ensure_one()
        self.incident_id.sudo().write({
            'confidential_user_ids': [(6, 0, self.user_ids.ids)],
        })
        # Log who now has access
        if self.user_ids:
            names = ', '.join(self.user_ids.mapped('name'))
            body = _('Confidential access list updated. Authorised users: %s') % names
        else:
            body = _('Confidential access list cleared — no additional users authorised. '
                     'Only the reporter, responsible manager, and users with the '
                     'Confidential Bypass permission can view this record.')
        self.incident_id.message_post(body=body, subtype_xmlid='mail.mt_note')
        return {'type': 'ir.actions.act_window_close'}

    def action_discard(self):
        return {'type': 'ir.actions.act_window_close'}

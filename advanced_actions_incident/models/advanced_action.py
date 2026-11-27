from odoo import api, fields, models


class AdvancedAction(models.Model):
    _inherit = 'advanced.action'

    source_app = fields.Selection(
        selection_add=[('incident', 'Incidents')], ondelete={'incident': 'set default'},
    )
    incident_id = fields.Many2one(
        'incident.report', string='Incident', ondelete='cascade', index='btree_not_null',
    )
    icam_finding_id = fields.Many2one(
        'incident.icam.finding', string='Related ICAM Finding', ondelete='set null',
        domain="[('incident_id', '=', incident_id)]",
        help='Link this action to a specific ICAM finding (optional).',
    )
    control_type_id = fields.Many2one(
        'incident.control.type', string='Control Type',
        help='Hierarchy of Controls classification for this corrective action.',
    )
    verification_required = fields.Boolean('Requires Verification')
    verified_by_id = fields.Many2one('res.users', string='Verified By', domain=[('share', '=', False)])
    verification_date = fields.Date('Verification Date')
    completion_notes = fields.Text('Notes / Evidence of Completion')

    @api.model
    def _action_sources(self):
        return super()._action_sources() + [('incident_id', 'incident')]

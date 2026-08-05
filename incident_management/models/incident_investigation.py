# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class IncidentIcamFinding(models.Model):
    """A single ICAM finding row — links an ICAM category + factor to the incident
    with a free-text description of how it contributed."""
    _name = 'incident.icam.finding'
    _description = 'ICAM Investigation Finding'
    _order = 'sequence, icam_category_id, id'

    incident_id = fields.Many2one(
        'incident.report', string='Incident',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    icam_category_id = fields.Many2one(
        'icam.category', string='ICAM Category', required=True)
    icam_factor_id = fields.Many2one(
        'icam.factor', string='Contributing Factor', required=True,
        domain="[('category_id', '=', icam_category_id)]")
    description = fields.Text(
        'How Did This Factor Contribute?', required=True,
        help='Explain specifically how this factor contributed to the incident.')
    is_root_cause = fields.Boolean(
        'Root Cause',
        help='Tick if this finding represents a root cause of the incident.')

    # Convenience relational fields for list display
    icam_category_name = fields.Char(
        related='icam_category_id.name', string='Category')
    icam_factor_name = fields.Char(
        related='icam_factor_id.name', string='Factor')


class IncidentCorrectiveAction(models.Model):
    """A corrective action arising from an incident investigation."""
    _name = 'incident.corrective.action'
    _description = 'Incident Corrective Action'
    _inherit = ['mail.thread']
    _order = 'priority desc, due_date, id'
    _rec_name = 'name'

    incident_id = fields.Many2one(
        'incident.report', string='Incident',
        required=True, ondelete='cascade', index=True)
    icam_finding_id = fields.Many2one(
        'incident.icam.finding', string='Related ICAM Finding',
        domain="[('incident_id', '=', incident_id)]",
        help='Link this action to a specific ICAM finding (optional).')

    name = fields.Text('Action Description', required=True)
    action_type = fields.Selection([
        ('eliminate', 'Eliminate'),
        ('substitute', 'Substitute'),
        ('engineering', 'Engineering Control'),
        ('administrative', 'Administrative Control'),
        ('ppe', 'Personal Protective Equipment'),
        ('other', 'Other'),
    ], string='Control Type',
        help='Hierarchy of Controls classification for this corrective action.')
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Important'),
        ('2', 'Very Important'),
        ('3', 'Critical'),
    ], default='0', string='Priority')
    responsible_id = fields.Many2one(
        'res.users', string='Responsible Person',
        required=True, domain=[('share', '=', False)])
    due_date = fields.Date('Due Date', required=True)
    state = fields.Selection([
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('done', 'Completed'),
    ], default='open', string='Status', tracking=True)
    completion_date = fields.Date('Completion Date', readonly=True, copy=False)
    verification_required = fields.Boolean('Requires Verification')
    verified_by_id = fields.Many2one(
        'res.users', string='Verified By', domain=[('share', '=', False)])
    verification_date = fields.Date('Verification Date')
    notes = fields.Text('Notes / Evidence of Completion')
    is_overdue = fields.Boolean(
        'Overdue', compute='_compute_is_overdue', store=False)

    @api.depends('due_date', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for rec in self:
            rec.is_overdue = (
                rec.state != 'done'
                and bool(rec.due_date)
                and rec.due_date < today
            )

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_done(self):
        self.write({
            'state': 'done',
            'completion_date': fields.Date.today(),
        })

    def action_reopen(self):
        self.write({'state': 'open', 'completion_date': False})

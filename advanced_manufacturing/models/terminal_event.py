# -*- coding: utf-8 -*-
from odoo import fields, models

# Technical: what the Work Centre app recorded (code depends on these values).
ACTIONS = [
    ('start', 'Start'),
    ('pause', 'Pause'),
    ('produce', 'Record Production'),
    ('finish', 'Finish'),
    ('qa', 'QA Checklist'),
    ('other', 'Other'),
]


class TerminalEvent(models.Model):
    """What workers recorded on the Work Centre app, online or synced after
    working offline. Each event is applied once (by its id from the app), so
    a re-sent offline event can't be recorded twice."""
    _name = 'advanced.manufacturing.terminal.event'
    _description = 'Work Centre App Event'
    _order = 'event_time desc, id desc'

    name = fields.Char(string='Event ID', required=True, readonly=True, index=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Centre', required=True, readonly=True,
                                    ondelete='cascade', index=True)
    company_id = fields.Many2one(related='workcenter_id.company_id', store=True)
    employee_id = fields.Many2one('hr.employee', string='Worker', readonly=True, ondelete='set null')
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order', readonly=True, ondelete='set null')
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', readonly=True,
                                    ondelete='set null', index='btree_not_null')
    action = fields.Selection(ACTIONS, required=True, readonly=True)
    event_time = fields.Datetime(string='Recorded At', required=True, readonly=True,
                                 help='When the worker did it (on the device).')
    create_date = fields.Datetime(string='Received At', readonly=True)
    offline = fields.Boolean(string='Recorded Offline', readonly=True)
    state = fields.Selection([('done', 'Applied'), ('failed', 'Failed')], string='Status', required=True, readonly=True)
    message = fields.Text(readonly=True)

    _name_workcenter_uniq = models.Constraint(
        'UNIQUE (name, workcenter_id)', 'This event was already recorded.')

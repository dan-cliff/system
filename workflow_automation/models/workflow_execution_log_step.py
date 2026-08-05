# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class WfExecutionLogStep(models.Model):
    """Per-step detail record within a workflow execution log."""

    _name = 'wf.execution.log.step'
    _description = 'Workflow Execution Log Step'
    _order = 'sequence, id'
    _rec_name = 'step_name'

    execution_log_id = fields.Many2one(
        'wf.execution.log',
        string='Execution Log',
        required=True,
        ondelete='cascade',
        index=True,
    )
    step_id = fields.Many2one(
        'wf.step',
        string='Step',
        ondelete='set null',
        help='Reference to the workflow step definition. May be null if the step was deleted.',
    )
    step_name = fields.Char(string='Step Name', required=True)
    step_type = fields.Char(string='Step Type')
    sequence = fields.Integer(string='Sequence')

    state = fields.Selection(
        selection=[
            ('success', 'Success'),
            ('skipped', 'Skipped'),
            ('stopped', 'Stopped'),
            ('error', 'Error'),
        ],
        string='State',
    )

    started_at = fields.Datetime(string='Started At')
    ended_at = fields.Datetime(string='Ended At')
    duration_ms = fields.Integer(string='Duration (ms)')

    result_summary = fields.Text(string='Result Summary')
    error_message = fields.Text(string='Error Message')
    stored_variable_name = fields.Char(string='Variable Stored')

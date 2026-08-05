# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class WfExecutionLog(models.Model):
    """Execution log for a single workflow run on a single trigger record.

    One log record is created per (workflow × trigger-record) execution.
    Child ``wf.execution.log.step`` records capture per-step details.
    """

    _name = 'wf.execution.log'
    _description = 'Workflow Execution Log'
    _order = 'started_at desc, id desc'
    _rec_name = 'trigger_record_name'

    workflow_id = fields.Many2one(
        'wf.automation',
        string='Workflow',
        required=True,
        ondelete='cascade',
        index=True,
    )
    trigger_model = fields.Char(string='Trigger Model', required=True)
    trigger_record_id = fields.Integer(
        string='Trigger Record ID',
        index=True,
        help='ID of the record that triggered the workflow. Stored as a plain integer '
             'because the record may have been deleted.',
    )
    trigger_record_name = fields.Char(string='Trigger Record')
    trigger_type = fields.Char(string='Trigger Event')

    state = fields.Selection(
        selection=[
            ('running', 'Running'),
            ('success', 'Success'),
            ('error', 'Error'),
            ('partial', 'Partial (some steps failed)'),
        ],
        string='State',
        default='running',
        required=True,
    )

    started_at = fields.Datetime(
        string='Started At',
        default=fields.Datetime.now,
    )
    ended_at = fields.Datetime(string='Ended At')
    duration_ms = fields.Integer(string='Duration (ms)')

    error_message = fields.Text(string='Error Message')

    step_log_ids = fields.One2many(
        'wf.execution.log.step',
        'execution_log_id',
        string='Step Logs',
    )
    steps_total = fields.Integer(string='Total Steps', default=0)
    steps_executed = fields.Integer(string='Executed', default=0)
    steps_skipped = fields.Integer(string='Skipped', default=0)

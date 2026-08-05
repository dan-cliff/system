# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

import logging

from odoo import fields, models
from odoo.tools import safe_eval

_logger = logging.getLogger(__name__)


class WfStepConnection(models.Model):
    """An explicit directed connection between two workflow steps.

    When a workflow has at least one connection the execution engine switches
    from simple sequence-order execution to BFS graph traversal: after each
    step the engine evaluates outgoing connections and follows those whose
    condition evaluates to True.
    """

    _name = 'wf.step.connection'
    _description = 'Workflow Step Connection'
    _order = 'sequence, id'

    workflow_id = fields.Many2one(
        'wf.automation',
        string='Workflow',
        related='from_step_id.workflow_id',
        store=True,
        index=True,
        readonly=True,
    )
    from_step_id = fields.Many2one(
        'wf.step',
        string='From Step',
        required=True,
        ondelete='cascade',
        index=True,
    )
    to_step_id = fields.Many2one(
        'wf.step',
        string='To Step',
        required=True,
        ondelete='cascade',
        index=True,
    )
    label = fields.Char(string='Label')
    sequence = fields.Integer(string='Sequence', default=10,
                              help='When multiple connections leave the same step, '
                                   'lower sequence connections are evaluated first.')

    condition_type = fields.Selection(
        selection=[
            ('none', 'Always'),
            ('domain', 'Domain Filter'),
            ('expression', 'Python Expression'),
        ],
        string='Condition',
        default='none',
        required=True,
    )
    condition_domain = fields.Char(
        string='Condition Domain',
        default='[]',
        help='Odoo domain evaluated against the trigger record.',
    )

    # Exposes the workflow's trigger model name so the domain widget can
    # present a graphical field/value builder.
    workflow_model_name = fields.Char(
        string='Workflow Model Name',
        related='from_step_id.workflow_id.model_name',
        readonly=True,
        store=False,
        help='Technical model name of the workflow trigger model (feeds domain widget).',
    )
    condition_expression = fields.Text(
        string='Condition Expression',
        help='Python expression that must return True to follow this connection.\n'
             'Available: record, env, user, variables, old_values.',
    )

    def evaluate(self, record, run_context):
        """Return True if this connection should be followed for *record*.

        Both domain and expression conditions receive a full eval context so
        that dynamic references like ``record.stage_id.name``, ``variables.*``,
        ``user``, etc. work correctly in connection filter expressions.
        """
        self.ensure_one()
        if self.condition_type == 'none':
            return True

        # Build eval context (shared by both domain and expression modes)
        eval_ctx = {
            'record': record,
            'env': record.env,
            'user': record.env.user,
            'variables': run_context.get('variables', {}),
            'old_values': run_context.get('old_values', {}),
        }
        # Also expose each variable at the top level for convenience
        eval_ctx.update(run_context.get('variables', {}))

        if self.condition_type == 'domain':
            try:
                # safe_eval parses the domain string; passing eval_ctx allows
                # dynamic values (e.g. [('state', '=', variables.get('st'))])
                domain = safe_eval.safe_eval(self.condition_domain or '[]', eval_ctx)
                return bool(record.filtered_domain(domain))
            except Exception:
                _logger.exception(
                    "wf.step.connection %d — error evaluating domain condition", self.id
                )
                return False

        if self.condition_type == 'expression':
            try:
                return bool(safe_eval.safe_eval(
                    self.condition_expression or 'True', eval_ctx
                ))
            except Exception:
                _logger.exception(
                    "wf.step.connection %d — error evaluating expression condition", self.id
                )
                return False

        return True

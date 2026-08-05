# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, fields, models
from odoo.tools import safe_eval

_logger = logging.getLogger(__name__)


class WfStepApiBodyParam(models.Model):
    """A single key/value pair for the JSON body of a Workflow API Call step.

    Used when the step's ``api_body_type`` is ``'key_value'``.  Each row
    contributes one JSON key to the outbound request body.

    Value types
    -----------
    ``static``
        A literal string value typed directly into the field.
    ``record_field``
        A dot-separated attribute path navigated from the trigger record
        (e.g. ``partner_id.email`` → ``record.partner_id.email``).
        Odoo recordsets are coerced to ``display_name`` (single) or a list
        of IDs (multi).  Datetime values are ISO-formatted.
    ``variable``
        A workflow variable stored by a previous step via
        ``store_result_var``.  Resolved from the run context at execution
        time.
    ``expression``
        A Python expression evaluated with ``safe_eval`` in the standard
        step context (``record``, ``variables``, ``env``).
    """

    _name = 'wf.step.api.body.param'
    _description = 'Workflow Step — API Body Parameter'
    _order = 'sequence, id'

    step_id = fields.Many2one(
        'wf.step',
        string='Step',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)

    key = fields.Char(
        string='Key',
        required=True,
        help='JSON key name in the request body.',
    )

    value_type = fields.Selection(
        selection=[
            ('static',       'Static Value'),
            ('record_field', 'Record Field'),
            ('variable',     'Variable'),
            ('expression',   'Expression'),
        ],
        string='Value Type',
        required=True,
        default='static',
    )

    static_value = fields.Char(
        string='Static Value',
        help='Plain text value to include for this key.',
    )
    record_field_path = fields.Char(
        string='Field Path',
        help=(
            'Dot-separated path from the trigger record.\n'
            'Example: partner_id.email  →  record.partner_id.email'
        ),
    )
    variable_name = fields.Char(
        string='Variable Name',
        help='Name of a workflow variable set by a previous step.',
    )
    expression_value = fields.Char(
        string='Expression',
        help='Python expression evaluated in the step context (safe_eval).',
    )

    # Computed preview shown in the list column
    value_preview = fields.Char(
        string='Resolved As',
        compute='_compute_value_preview',
        store=False,
    )

    @api.depends(
        'value_type', 'static_value', 'record_field_path',
        'variable_name', 'expression_value',
    )
    def _compute_value_preview(self):
        for rec in self:
            if rec.value_type == 'static':
                rec.value_preview = rec.static_value or ''
            elif rec.value_type == 'record_field':
                rec.value_preview = (
                    '{{record.%s}}' % rec.record_field_path
                    if rec.record_field_path else '{{record.…}}'
                )
            elif rec.value_type == 'variable':
                rec.value_preview = (
                    '{{variables.%s}}' % rec.variable_name
                    if rec.variable_name else '{{variables.…}}'
                )
            else:  # expression
                rec.value_preview = rec.expression_value or ''

    # ------------------------------------------------------------------ #
    # Runtime resolution                                                   #
    # ------------------------------------------------------------------ #

    def resolve_value(self, record, run_context):
        """Resolve this parameter to its actual value at execution time.

        Parameters
        ----------
        record : odoo.models.Model
            The trigger record from the workflow execution.
        run_context : dict
            Current workflow run context (contains ``variables`` dict etc.).

        Returns
        -------
        object
            The resolved value — any JSON-serialisable Python type.
        """
        self.ensure_one()
        vtype = self.value_type

        if vtype == 'static':
            return self.static_value or ''

        if vtype == 'record_field':
            return self._navigate_record_path(record, self.record_field_path or '')

        if vtype == 'variable':
            var_name = (self.variable_name or '').strip()
            return run_context.get('variables', {}).get(var_name)

        if vtype == 'expression':
            expr = (self.expression_value or '').strip()
            if not expr:
                return None
            eval_ctx = {
                'record': record,
                'variables': run_context.get('variables', {}),
                'env': record.env,
                'uid': record.env.uid,
            }
            try:
                return safe_eval.safe_eval(expr, eval_ctx)
            except Exception:
                _logger.exception(
                    'wf.step.api.body.param — error evaluating expression "%s"', expr
                )
                return None

        return None

    @staticmethod
    def _navigate_record_path(record, path):
        """Navigate *path* (dot-separated) from *record* and return the value.

        Odoo recordsets are unwrapped:
        * Single record  → ``display_name`` string
        * Many records   → list of IDs
        * Empty record   → ``None``
        Datetime / Date objects are ISO-formatted.  All other types are
        returned as-is.
        """
        if not path:
            return None
        val = record
        try:
            for segment in path.split('.'):
                if val is None:
                    return None
                if isinstance(val, dict):
                    val = val.get(segment)
                else:
                    val = getattr(val, segment, None)
        except Exception:
            _logger.warning(
                'wf.step.api.body.param — could not navigate field path "%s"', path
            )
            return None

        # Coerce Odoo recordsets
        if hasattr(val, '_name'):
            if len(val) == 0:
                return None
            if len(val) == 1:
                return val.display_name if hasattr(val, 'display_name') else val.id
            return [r.id for r in val]

        # Coerce datetime / date to ISO string so json.dumps works
        import datetime
        if isinstance(val, (datetime.datetime, datetime.date)):
            return val.isoformat()

        return val

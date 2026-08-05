# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import safe_eval

_logger = logging.getLogger(__name__)


class WfStepFieldMapping(models.Model):
    """A single field-value assignment belonging to a workflow step.

    Used by 'create_record' and 'update_record' step types to specify what
    value should be written to a given field on the target record.
    """

    _name = 'wf.step.field.mapping'
    _description = 'Workflow Step Field Mapping'
    _order = 'id'

    step_id = fields.Many2one(
        'wf.step',
        string='Step',
        required=True,
        ondelete='cascade',
        index=True,
    )
    field_id = fields.Many2one(
        'ir.model.fields',
        string='Field',
        required=True,
        ondelete='cascade',
    )
    value_type = fields.Selection(
        selection=[
            ('static', 'Static Value'),
            ('expression', 'Python Expression'),
            ('record_field', 'Record Field Path'),
            ('variable', 'Context Variable'),
        ],
        string='Value Source',
        default='static',
        required=True,
    )
    static_value = fields.Char(string='Static Value')
    expression_value = fields.Text(
        string='Python Expression',
        help='Python expression evaluated with the standard workflow eval context.',
    )
    record_field_path = fields.Char(
        string='Record Field Path',
        help='Dot-path traversal on the trigger record, e.g. "partner_id.name".',
    )
    variable_name = fields.Char(
        string='Variable Name',
        help='Name of a context variable set by a previous step.',
    )
    m2m_operation = fields.Selection(
        selection=[
            ('set', 'Replace (set)'),
            ('add', 'Add'),
            ('remove', 'Remove'),
            ('clear', 'Clear all'),
        ],
        string='M2M Operation',
        default='set',
        help='How to apply the value for Many2many fields.',
    )

    # ------------------------------------------------------------------ #
    # Value resolution                                                     #
    # ------------------------------------------------------------------ #

    def resolve_value(self, record, run_context):
        """Resolve and return the Python value to write for this mapping.

        Args:
            record: The trigger record (browse object).
            run_context: The workflow run context dict.

        Returns:
            A Python value suitable for passing to ORM write()/create().
        """
        self.ensure_one()
        field_obj = self.field_id
        ttype = field_obj.ttype

        raw = self._get_raw_value(record, run_context)

        # Handle Many2many specially
        if ttype == 'many2many':
            return self._build_m2m_command(raw)

        # Handle Many2one — return int (record ID)
        if ttype == 'many2one':
            if hasattr(raw, 'id'):
                return raw.id
            if isinstance(raw, models.BaseModel):
                return raw.id if raw else False
            try:
                return int(raw) if raw not in (None, False, '') else False
            except (TypeError, ValueError):
                return False

        # Coerce scalars for common types
        if ttype == 'integer':
            try:
                return int(raw) if raw not in (None, False, '') else False
            except (TypeError, ValueError):
                return False
        if ttype == 'float':
            try:
                return float(raw) if raw not in (None, False, '') else False
            except (TypeError, ValueError):
                return False
        if ttype == 'boolean':
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, str):
                return raw.lower() in ('1', 'true', 'yes')
            return bool(raw)

        return raw

    def _get_raw_value(self, record, run_context):
        """Return the raw (un-coerced) value according to ``value_type``."""
        vtype = self.value_type

        if vtype == 'static':
            return self.static_value

        if vtype == 'expression':
            if not self.expression_value:
                return False
            step = self.step_id
            eval_ctx = step._get_eval_context(record, run_context)
            try:
                return safe_eval.safe_eval(self.expression_value, eval_ctx)
            except Exception:
                _logger.exception(
                    "wf.step.field.mapping — error evaluating expression '%s'",
                    self.expression_value,
                )
                return False

        if vtype == 'record_field':
            if not self.record_field_path:
                return False
            try:
                val = record
                for part in self.record_field_path.split('.'):
                    if not val:
                        return False
                    val = val[part] if hasattr(val, '__getitem__') else getattr(val, part, False)
                return val
            except Exception:
                _logger.exception(
                    "wf.step.field.mapping — error traversing field path '%s'",
                    self.record_field_path,
                )
                return False

        if vtype == 'variable':
            if not self.variable_name:
                return False
            return run_context.get('variables', {}).get(self.variable_name, False)

        return False

    def _build_m2m_command(self, raw):
        """Build a Many2many Command list from *raw* based on ``m2m_operation``."""
        op = self.m2m_operation or 'set'

        # Normalise raw to a list of integer IDs
        ids = []
        if isinstance(raw, models.BaseModel):
            ids = raw.ids
        elif isinstance(raw, (list, tuple)):
            ids = [int(x) if not hasattr(x, 'id') else x.id for x in raw if x]
        elif raw:
            try:
                ids = [int(raw)]
            except (TypeError, ValueError):
                ids = []

        if op == 'set':
            return [fields.Command.set(ids)]
        if op == 'add':
            return [fields.Command.link(i) for i in ids]
        if op == 'remove':
            return [fields.Command.unlink(i) for i in ids]
        if op == 'clear':
            return [fields.Command.clear()]
        return [fields.Command.set(ids)]

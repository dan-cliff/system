# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import safe_eval

_logger = logging.getLogger(__name__)


# Triggers that operate against a specific record — require the user to
# pick a test record before the workflow can be exercised.
_RECORD_TRIGGERS = frozenset({
    'on_create', 'on_write', 'on_create_or_write',
    'on_unlink', 'on_stage_change', 'on_state_change',
})


class WfManualRunWizard(models.TransientModel):
    """Wizard for test-running a record-based workflow against a chosen record.

    The user can either enter a single Record ID (the common "test one record"
    case) or switch to a domain filter to target multiple records at once.
    """

    _name = 'wf.manual.run.wizard'
    _description = 'Workflow Test Run Wizard'

    workflow_id = fields.Many2one(
        'wf.automation',
        string='Workflow',
        required=True,
        readonly=True,
    )
    model_name = fields.Char(
        string='Model',
        compute='_compute_model_name',
        store=False,
    )
    # ── Single-record mode (default) ──────────────────────────────────── #
    record_id = fields.Integer(
        string='Record ID',
        help='ID of the specific record to test this workflow against.',
    )
    record_display_name = fields.Char(
        string='Record',
        compute='_compute_record_display_name',
        store=False,
        help='Display name of the selected record (resolved from Record ID).',
    )
    # ── Domain mode ───────────────────────────────────────────────────── #
    use_domain = fields.Boolean(
        string='Use Domain Filter Instead',
        default=False,
        help='Switch to a domain filter to test against multiple records at once.',
    )
    domain = fields.Char(
        string='Domain',
        default='[]',
        help='Odoo domain used to select test records.',
    )
    # ── Summary ───────────────────────────────────────────────────────── #
    record_count = fields.Integer(
        string='Records Found',
        compute='_compute_record_count',
        store=False,
    )

    # ------------------------------------------------------------------ #
    # Computed fields                                                      #
    # ------------------------------------------------------------------ #

    @api.depends('workflow_id')
    def _compute_model_name(self):
        for rec in self:
            rec.model_name = rec.workflow_id.sudo().model_name or ''

    @api.depends('workflow_id', 'record_id', 'use_domain', 'domain')
    def _compute_record_display_name(self):
        for rec in self:
            if rec.use_domain or not rec.record_id or not rec.model_name:
                rec.record_display_name = ''
                continue
            try:
                Model = self.env.get(rec.model_name)
                if Model is None:
                    rec.record_display_name = ''
                    continue
                target = Model.browse(rec.record_id)
                if target.exists():
                    rec.record_display_name = target.sudo().display_name or str(rec.record_id)
                else:
                    rec.record_display_name = _('(record #%d not found)', rec.record_id)
            except Exception:
                rec.record_display_name = ''

    @api.depends('workflow_id', 'record_id', 'use_domain', 'domain')
    def _compute_record_count(self):
        for rec in self:
            try:
                records = rec._resolve_records()
                rec.record_count = len(records)
            except Exception:
                rec.record_count = 0

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _resolve_records(self):
        """Return the recordset this wizard should run the workflow against."""
        self.ensure_one()
        wf_sudo = self.workflow_id.sudo()
        model_name = wf_sudo.model_name
        if not model_name:
            return self.env['res.lang'].browse()

        Model = self.env.get(model_name)
        if Model is None:
            raise UserError(_("Model '%s' not found.") % model_name)

        if self.use_domain:
            try:
                domain = safe_eval.safe_eval(self.domain or '[]', {})
            except Exception as exc:
                raise UserError(
                    _("Invalid domain expression: %s") % str(exc)
                ) from exc
            return Model.search(domain)

        # Single-record mode
        if self.record_id:
            record = Model.browse(self.record_id)
            if not record.exists():
                raise UserError(
                    _("Record #%d was not found in model '%s'.")
                    % (self.record_id, model_name)
                )
            return record

        raise UserError(_("Please enter a Record ID or switch to a domain filter."))

    # ------------------------------------------------------------------ #
    # Action                                                               #
    # ------------------------------------------------------------------ #

    def action_run(self):
        """Execute the workflow on the selected test record(s) and close the wizard."""
        self.ensure_one()
        records = self._resolve_records()

        if not records:
            raise UserError(_("No matching records found."))

        wf_name = self.workflow_id.sudo().name
        _logger.info(
            "wf.manual.run.wizard — test-running '%s' on %d record(s) of '%s'",
            wf_name,
            len(records),
            records._name,
        )

        self.workflow_id._process(records, 'manual')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Test Run Complete'),
                'message': _(
                    'Workflow "%s" was run on %d record(s). '
                    'Check the Runs log for step-by-step results.',
                    wf_name,
                    len(records),
                ),
                'sticky': False,
                'type': 'success',
            },
        }

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DevAiMixin(models.AbstractModel):
    """AI actions run from the form behind the progress overlay (CLAUDE.md > AI functions).

    A model lists its AI jobs in ``_dev_ai_jobs`` ({key: method name}); the
    ``dev_ai_action`` widget saves the record, asks ``get_ai_job_info`` how to word
    the steps, runs ``action_ai_run`` and reloads the record. Each job method
    ``_ai_<key>`` returns a message for the success notification, and
    ``_ai_<key>_info`` returns {'title': ..., 'step': ...} for the overlay.
    """
    _name = 'dev.ai.mixin'
    _description = 'Development AI Actions'
    _dev_ai_jobs = ()

    ai_available = fields.Boolean(compute='_compute_ai_available',
                                  help='An AI key (Claude or Gemini) is set, so the AI buttons show.')

    def _compute_ai_available(self):
        available = self.env['dev.ai']._available()
        for record in self:
            record.ai_available = available

    def _check_ai_job(self, job):
        if job not in self._dev_ai_jobs:
            raise UserError(_('Unknown AI action: %s', job))
        self.env['dev.ai']._check_available()

    def get_ai_job_info(self, job):
        """Title and AI step of a job, worded for the progress overlay."""
        self.ensure_one()
        self._check_ai_job(job)
        self.check_access('write')
        info = getattr(self, '_ai_%s_info' % job)()
        info.setdefault('provider', self.env['dev.ai']._provider_label())
        return info

    def action_ai_run(self, job):
        self.ensure_one()
        self._check_ai_job(job)
        self.check_access('write')
        return getattr(self, '_ai_%s' % job)() or _('Done.')

    @api.model
    def _ai_json(self, prompt, system='', max_tokens=4000):
        return self.env['dev.ai']._request_json(prompt, system=system, max_tokens=max_tokens)

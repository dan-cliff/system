from odoo import api, fields, models

from .dev_release import DEFAULT_DAYS, PARAM_PROMPT


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dev_release_name_prompt = fields.Char(
        'Release Naming Prompt', config_parameter=PARAM_PROMPT,
        help='When set (and an AI key is set), every new release is named by the AI following this prompt, '
             'e.g. "Stars and planets" or "Famous people from history", and its Trivia is filled in.')
    dev_sprint_days = fields.Integer('Sprint Length', config_parameter='dev_management.sprint_days',
                                     default=DEFAULT_DAYS['sprint_days'],
                                     help='Days from the Start Date (a Monday) to the End Date, both included.')
    dev_alpha_days = fields.Integer('Alpha Release After', config_parameter='dev_management.alpha_days',
                                    default=DEFAULT_DAYS['alpha_days'], help='Days after the End Date.')
    dev_beta_days = fields.Integer('Beta Release After', config_parameter='dev_management.beta_days',
                                   default=DEFAULT_DAYS['beta_days'], help='Days after the Alpha Release.')
    dev_core_days = fields.Integer('Core Release After', config_parameter='dev_management.core_days',
                                   default=DEFAULT_DAYS['core_days'], help='Days after the Beta Release.')
    dev_ai_available = fields.Boolean(compute='_compute_dev_ai')
    dev_ai_provider = fields.Char(compute='_compute_dev_ai')

    @api.depends('company_id')
    def _compute_dev_ai(self):
        available = self.env['dev.ai']._available()
        provider = self.env['dev.ai']._provider_label()
        for settings in self:
            settings.dev_ai_available = available
            settings.dev_ai_provider = provider

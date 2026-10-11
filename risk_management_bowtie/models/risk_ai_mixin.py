from odoo import models


class RiskAiMixin(models.AbstractModel):
    _inherit = 'risk.ai.mixin'

    # A bowtie per risk roughly doubles the response, so allow a longer answer.
    _ai_max_tokens = 16000
    _ai_timeout = 300

    def _ai_build_prompt(self, existing_types, existing_subtypes, existing_controls, likelihoods, consequences):
        prompt = super()._ai_build_prompt(
            existing_types, existing_subtypes, existing_controls, likelihoods, consequences,
        )
        barrier_types = self.env['risk.bowtie.barrier.type'].search([]).mapped('name')
        effectiveness = self.env['risk.bowtie.barrier.effectiveness'].search([]).mapped('name')
        return prompt + self.env['risk.line.mixin']._ai_build_bowtie_prompt(
            barrier_types, effectiveness, consequences,
        )

    def get_ai_generate_description(self):
        return super().get_ai_generate_description() + ", and each risk's bowtie (threats and consequences)"

    def _ai_line_vals(self, risk, vals):
        vals = super()._ai_line_vals(risk, vals)
        vals.update(self.env['risk.line.mixin']._ai_bowtie_vals(risk.get('bowtie')))
        return vals

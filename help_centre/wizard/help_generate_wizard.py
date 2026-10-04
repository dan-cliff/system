from odoo import _, api, fields, models
from odoo.exceptions import UserError


_STYLE_OPTIONS = [
    ('tutorial', 'Step-by-Step Tutorial'),
    ('overview', 'Feature Overview'),
    ('faq', 'FAQ / Q&A Format'),
    ('quick', 'Quick Reference Guide'),
    ('troubleshoot', 'Troubleshooting Guide'),
]

_AUDIENCE_LABELS = {
    'internal': 'Internal Odoo users (administrators / power users)',
    'external': 'External / public users (customers, general public)',
    'both': 'Mixed audience (internal and external users)',
}


class HelpGenerateWizard(models.TransientModel):
    _name = 'help.generate.wizard'
    _description = 'Generate Help Article with AI'

    # ── Step 1: Prompt ────────────────────────────────────────────────────────

    article_id = fields.Many2one('help.article', 'Target Article', required=True)
    topic = fields.Text(
        'Topic / Prompt', required=True,
        help='Describe what this article should cover. Be as specific as possible.\n'
             'Example: "How to create a purchase order and receive goods into stock in Odoo 19"',
    )
    audience = fields.Selection([
        ('internal', 'Internal Only'),
        ('external', 'External / Public'),
        ('both', 'Both (Internal & External)'),
    ], default='internal', required=True)
    module_ids = fields.Many2many(
        'ir.module.module', string='Related Odoo Modules',
        domain=[('state', '=', 'installed')],
    )
    style = fields.Selection(_STYLE_OPTIONS, string='Article Style', default='tutorial', required=True)
    extra_instructions = fields.Text(
        'Additional Instructions',
        help='Optional extra guidance for the AI, e.g. "Focus on the warehouse manager workflow" '
             'or "Include screenshots callouts using Bootstrap alert boxes".',
    )

    # ── Step 2: Generated content ─────────────────────────────────────────────

    wizard_state = fields.Selection([
        ('prompt', 'Enter Prompt'),
        ('generated', 'Review & Apply'),
    ], default='prompt', required=True)

    generated_content = fields.Html(
        'Generated Content',
        sanitize=False,
        help='AI-generated HTML. Review and edit before applying to the article.',
    )

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_generate(self):
        """Call the AI and store the result in generated_content."""
        self.ensure_one()

        if not self.topic or not self.topic.strip():
            raise UserError(_('Please enter a topic / prompt before generating.'))

        module_names = ', '.join(self.module_ids.mapped('shortdesc') or self.module_ids.mapped('name')) if self.module_ids else ''
        audience_label = _AUDIENCE_LABELS.get(self.audience, self.audience)
        style_label = dict(_STYLE_OPTIONS).get(self.style, '')

        prompt = self.topic
        if self.extra_instructions:
            prompt += f'\n\nAdditional instructions: {self.extra_instructions}'

        ai = self.env['help.ai.service']
        content = ai.generate_article(
            topic=prompt,
            audience_label=audience_label,
            module_names=module_names,
            style_hint=style_label,
        )

        self.write({
            'generated_content': content,
            'wizard_state': 'generated',
        })

        # Re-open the wizard on the same record to show the preview
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generate Article with AI'),
            'res_model': 'help.generate.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply(self):
        """Write the generated HTML to the target article."""
        self.ensure_one()
        if not self.generated_content:
            raise UserError(_('No content to apply. Please generate content first.'))

        module_names = ', '.join(
            self.module_ids.mapped('shortdesc') or self.module_ids.mapped('name')
        ) if self.module_ids else ''

        self.article_id.write({
            'content': self.generated_content,
            'audience': self.audience,
            'ai_generated': True,
            'ai_prompt': self.topic,
        })
        if self.module_ids:
            self.article_id.module_ids = self.module_ids

        return {'type': 'ir.actions.act_window_close'}

    def action_back(self):
        """Go back to the prompt step."""
        self.write({'wizard_state': 'prompt'})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generate Article with AI'),
            'res_model': 'help.generate.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

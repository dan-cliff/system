from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .risk_ai_mixin import ai_api_key, ai_generate_control_description


class RiskControl(models.Model):
    _name = 'risk.control'
    _description = 'Risk Control'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(help='Optional internal reference, e.g. from a control framework.')
    category_id = fields.Many2one('risk.category', string='Risk Category')
    hierarchy_id = fields.Many2one(
        'risk.control.hierarchy', string='Hierarchy of Controls',
    )
    description = fields.Text()
    active = fields.Boolean(default=True)
    ai_available = fields.Boolean(compute='_compute_ai_available')
    # When the background job last tried (and failed) to describe this control, so a
    # control the AI can't describe doesn't hold up the others on every run.
    ai_description_tried_at = fields.Datetime(copy=False, readonly=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'A control with this name already exists.',
    )

    def _compute_ai_available(self):
        available = bool(ai_api_key(self.env))
        for control in self:
            control.ai_available = available

    def action_ai_write_descriptions(self):
        """Write a description by AI for each of these controls that has none.

        Called from the Control form's "Write Description by AI" button and from the AI
        risk actions (for the controls they add), each showing the AI progress overlay.
        Returns the names of the controls described.
        """
        controls = self.filtered(lambda control: not control.description)
        if not controls:
            return []
        api_key = ai_api_key(self.env)
        if not api_key:
            raise UserError('Set a Claude AI API Key first (Settings > General Settings > Claude AI).')
        controls.check_access('read')
        described = []
        for control in controls:
            description = ai_generate_control_description(api_key, control.name)
            if description:
                # sudo: users who may add Controls but not edit them still get the description.
                control.sudo().description = description
                described.append(control.name)
        return described

    @api.model
    def _cron_ai_write_missing_descriptions(self, limit=5):
        """Background job: describe controls added without a description (e.g. typed in by
        hand on a risk), a few at a time, so saving never waits on the AI."""
        api_key = ai_api_key(self.env)
        if not api_key:
            return
        retry_before = fields.Datetime.now() - timedelta(days=1)
        controls = self.search([
            ('description', '=', False),
            '|', ('ai_description_tried_at', '=', False), ('ai_description_tried_at', '<', retry_before),
        ], limit=limit, order='id')
        for control in controls:
            description = ai_generate_control_description(api_key, control.name)
            if description:
                control.description = description
            else:
                control.ai_description_tried_at = fields.Datetime.now()
            # Keep each finished control even if a later one times out the job.
            self.env.cr.commit()

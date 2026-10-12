from odoo import api, fields, models

from .social_ai import PARAM_AI_ANALYSIS, PARAM_AI_RECOMMENDATIONS, ai_credentials
from .social_invoice import PARAM_INTEGRATE_ACCOUNTS, PARAM_INVOICE_PRODUCT


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    social_integrate_accounts = fields.Boolean(
        string='Integrate to Accounts', config_parameter=PARAM_INTEGRATE_ACCOUNTS,
        help='Should Social Manager automatically create invoices for monetised content?')
    social_invoice_product_id = fields.Many2one(
        'product.product', string='Invoice Product', config_parameter=PARAM_INVOICE_PRODUCT,
        help='Product (and so income account and taxes) used on monetisation invoice lines. '
             'Leave empty to use the sales journal\'s default income account.')
    social_ai_analysis = fields.Boolean(
        string='AI Analysis', config_parameter=PARAM_AI_ANALYSIS,
        help='Should content be shared with the AI agent to monitor sentiment, potential '
             'moderation alerts and recommend actions?')
    social_ai_recommendations = fields.Boolean(
        string='AI Recommendations', config_parameter=PARAM_AI_RECOMMENDATIONS,
        help='Should the AI recommend post content for special events and upcoming company releases?')
    social_ai_key_set = fields.Boolean(compute='_compute_social_ai_key_set')

    @api.depends('company_id')
    def _compute_social_ai_key_set(self):
        key_set = bool(ai_credentials(self.env)[1])
        for settings in self:
            settings.social_ai_key_set = key_set

    def set_values(self):
        super().set_values()
        # The scheduled actions only run while their feature is on; their date and time are
        # set in Settings > Technical > Scheduled Actions.
        for xmlid, active in (
            ('social_manager.ir_cron_social_ai_recommendations', self.social_ai_recommendations),
            ('social_manager.ir_cron_social_ai_analyse', self.social_ai_analysis),
            ('social_manager.ir_cron_social_invoices', self.social_integrate_accounts),
        ):
            cron = self.env.ref(xmlid, raise_if_not_found=False)
            if cron and cron.active != bool(active):
                cron.sudo().active = bool(active)

    def action_social_open_cron(self):
        cron = self.env.ref('social_manager.ir_cron_social_ai_recommendations')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ir.cron',
            'res_id': cron.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_social_create_invoices(self):
        return self.env['ir.actions.act_window']._for_xml_id('social_manager.action_social_invoice_wizard')

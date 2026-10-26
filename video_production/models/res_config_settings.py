# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ─── Projects Integration ────────────────────────────────────────────
    vp_use_project = fields.Boolean(
        string='Projects Integration',
        config_parameter='video_production.use_project',
        help='Show project reference fields on Video Productions.',
    )

    # ─── Timesheets Integration ──────────────────────────────────────────
    vp_use_timesheets = fields.Boolean(
        string='Timesheets Integration',
        config_parameter='video_production.use_timesheets',
        help='Enable timesheet tracking on productions and edit jobs.',
    )

    # ─── To-Do Integration ───────────────────────────────────────────────
    vp_use_todo = fields.Boolean(
        string='To-Do Integration',
        config_parameter='video_production.use_todo',
        help='Allow creating To-Do tasks directly from productions.',
    )

    # ─── CRM Integration ─────────────────────────────────────────────────
    vp_use_crm = fields.Boolean(
        string='CRM Integration',
        config_parameter='video_production.use_crm',
        help='Show CRM opportunity link on Video Productions.',
    )

    # ─── Sales Integration ───────────────────────────────────────────────
    vp_use_sales = fields.Boolean(
        string='Sales Integration',
        config_parameter='video_production.use_sales',
        default=True,
        help='Show Sales Order link on Video Productions.',
    )

    # ─── Expenses Integration ────────────────────────────────────────────
    vp_use_expenses = fields.Boolean(
        string='Expenses Integration',
        config_parameter='video_production.use_expenses',
        help='Show expense tracking links on edit jobs and shoots.',
    )

    # ─── Maintenance / Equipment Integration ────────────────────────────
    vp_use_maintenance = fields.Boolean(
        string='Equipment / Asset Management',
        config_parameter='video_production.use_maintenance',
        help='Show maintenance equipment links on shoots.',
    )

    # ─── Purchase Ordering Integration ───────────────────────────────────
    vp_use_purchase = fields.Boolean(
        string='Purchase Ordering Integration',
        config_parameter='video_production.use_purchase',
        help='Show a Purchase Orders smart button on Video Productions '
             'and link productions to purchase orders.',
    )

    # ─── Social Marketing Integration ────────────────────────────────────
    vp_use_social = fields.Boolean(
        string='Social Marketing Integration',
        config_parameter='video_production.use_social',
        help='Enable Social Marketing integration for scheduling YouTube and social media posts.',
    )

    # ─── AI Integration ──────────────────────────────────────────────────
    vp_gemini_api_key = fields.Char(
        string='Gemini API Key (Video Production)',
        config_parameter='video_production.gemini_api_key',
        help='Your Google Gemini API key for AI content idea generation. '
             'Get your key from https://aistudio.google.com/apikey',
    )
    vp_gemini_from_ai_settings = fields.Boolean(
        string='Gemini Key from AI Settings',
        compute='_compute_vp_gemini_from_ai_settings',
        help='True when a Google Gemini key is configured in the central AI app settings.',
    )

    @api.depends_context('uid')
    def _compute_vp_gemini_from_ai_settings(self):
        key = self.env['ir.config_parameter'].sudo().get_param('ai.google_key', default='')
        for rec in self:
            rec.vp_gemini_from_ai_settings = bool(key)

    # ─── Module installs (optional modules) ─────────────────────────────
    # These fields trigger Odoo's built-in module install mechanism when True.
    # They are set automatically in set_values() — users never touch them.
    module_project = fields.Boolean(string='Install Projects Module')
    module_hr_timesheet = fields.Boolean(string='Install Timesheets Module')
    module_crm = fields.Boolean(string='Install CRM Module')
    module_sale_management = fields.Boolean(string='Install Sales Module')
    module_hr_expense = fields.Boolean(string='Install Expenses Module')
    module_maintenance = fields.Boolean(string='Install Maintenance / Equipment Module')
    module_social = fields.Boolean(string='Install Social Marketing Module')

    # Integration toggle -> module it installs.
    _VP_INTEGRATION_MODULES = {
        'vp_use_project': 'module_project',
        'vp_use_timesheets': 'module_hr_timesheet',
        'vp_use_crm': 'module_crm',
        'vp_use_expenses': 'module_hr_expense',
        'vp_use_maintenance': 'module_maintenance',
        'vp_use_social': 'module_social',
    }

    def set_values(self):
        # Turning an integration on queues the module it needs for installation, so users
        # never have to tick a separate checkbox. Only the switch from off to on does this:
        # an integration left on must not reinstall a module that was uninstalled since,
        # every time any settings page is saved.
        get = self.env['ir.config_parameter'].sudo().get_param
        for toggle, module_field in self._VP_INTEGRATION_MODULES.items():
            param = self._fields[toggle].config_parameter
            if self[toggle] and get(param, 'False') != 'True':
                self[module_field] = True
        super().set_values()

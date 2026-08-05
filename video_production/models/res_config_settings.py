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

    def set_values(self):
        # Enabling an integration automatically queues the required module for
        # installation. Users should never have to tick a separate checkbox.
        if self.vp_use_project:
            self.module_project = True
        if self.vp_use_timesheets:
            self.module_hr_timesheet = True
        if self.vp_use_crm:
            self.module_crm = True
        if self.vp_use_expenses:
            self.module_hr_expense = True
        if self.vp_use_maintenance:
            self.module_maintenance = True
        if self.vp_use_social:
            self.module_social = True
        super().set_values()

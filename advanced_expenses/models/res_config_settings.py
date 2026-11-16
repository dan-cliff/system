from odoo import api, fields, models

from . import expense_ai

# Integration toggle -> the app it works with (the toggle only shows when that app is installed).
INTEGRATIONS = {
    'module_advanced_expenses_account': 'account',
    'module_advanced_expenses_sale': 'sale',
    'module_advanced_expenses_project': 'project',
    'module_advanced_expenses_payroll': 'advanced_payroll',
}


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    expense_manager_approval = fields.Boolean(related='company_id.expense_manager_approval', readonly=False)
    expense_duplicate_warning = fields.Boolean(related='company_id.expense_duplicate_warning', readonly=False)

    module_advanced_expenses_account = fields.Boolean(string='Expenses in Accounting')
    module_advanced_expenses_sale = fields.Boolean(string='Re-invoice Expenses to Customers')
    module_advanced_expenses_project = fields.Boolean(string='Expenses on Projects')
    module_advanced_expenses_payroll = fields.Boolean(string='Reimburse Expenses through Payroll')

    expenses_has_account = fields.Boolean(compute='_compute_expenses_installed_apps')
    expenses_has_sale = fields.Boolean(compute='_compute_expenses_installed_apps')
    expenses_has_project = fields.Boolean(compute='_compute_expenses_installed_apps')
    expenses_has_payroll = fields.Boolean(compute='_compute_expenses_installed_apps')
    expenses_ai_available = fields.Boolean(compute='_compute_expenses_ai')
    expenses_ai_provider = fields.Char(compute='_compute_expenses_ai')

    @api.depends('company_id')
    def _compute_expenses_installed_apps(self):
        installed = set(self.env['ir.module.module'].sudo().search([
            ('name', 'in', list(INTEGRATIONS.values())), ('state', '=', 'installed'),
        ]).mapped('name'))
        for settings in self:
            settings.expenses_has_account = 'account' in installed
            settings.expenses_has_sale = 'sale' in installed
            settings.expenses_has_project = 'project' in installed
            settings.expenses_has_payroll = 'advanced_payroll' in installed

    @api.depends('company_id')
    def _compute_expenses_ai(self):
        available = expense_ai.ai_available(self.env)
        provider = expense_ai.provider_label(self.env) if available else ''
        for settings in self:
            settings.expenses_ai_available = available
            settings.expenses_ai_provider = provider

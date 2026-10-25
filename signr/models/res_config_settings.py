# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .signr_integration import INTEGRATIONS, PARAM, integration_models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # One switch per integration (see signr_integration.INTEGRATIONS), and
    # whether its app is installed.
    signr_integration_applicant = fields.Boolean(
        'Talent Applications', config_parameter=PARAM % 'applicant')
    signr_integration_crm_opportunity = fields.Boolean(
        'CRM Opportunities', config_parameter=PARAM % 'crm_opportunity')
    signr_integration_crm_contract = fields.Boolean(
        'CRM Sales', config_parameter=PARAM % 'crm_contract')
    signr_integration_sale_order = fields.Boolean(
        'Sales', config_parameter=PARAM % 'sale_order')
    signr_integration_employee_contract = fields.Boolean(
        'Employee Contracts', config_parameter=PARAM % 'employee_contract')
    signr_integration_employee = fields.Boolean(
        'Employees', config_parameter=PARAM % 'employee')
    signr_integration_incident = fields.Boolean(
        'Incidents', config_parameter=PARAM % 'incident')
    signr_integration_injury = fields.Boolean(
        'Injury Management', config_parameter=PARAM % 'injury')

    signr_available_applicant = fields.Boolean(compute='_compute_signr_available')
    signr_available_crm_opportunity = fields.Boolean(compute='_compute_signr_available')
    signr_available_crm_contract = fields.Boolean(compute='_compute_signr_available')
    signr_available_sale_order = fields.Boolean(compute='_compute_signr_available')
    signr_available_employee_contract = fields.Boolean(compute='_compute_signr_available')
    signr_available_employee = fields.Boolean(compute='_compute_signr_available')
    signr_available_incident = fields.Boolean(compute='_compute_signr_available')
    signr_available_injury = fields.Boolean(compute='_compute_signr_available')

    @api.depends('company_id')
    def _compute_signr_available(self):
        installed = set(self.env['ir.module.module'].sudo().search(
            [('state', '=', 'installed')]).mapped('name'))
        for settings in self:
            for key, model, modules, _title, _description in INTEGRATIONS:
                settings[f'signr_available_{key}'] = model in self.env and bool(installed.intersection(modules))

    def set_values(self):
        before = integration_models(self.env)
        super().set_values()
        if integration_models(self.env) != before:
            # the forms' smart buttons are part of the cached views
            self.env.registry.clear_cache('templates')

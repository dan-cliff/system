# -*- coding: utf-8 -*-
from odoo import api, models, tools

# Departments are read all over Odoo (every app shows people's departments).
# Personnel's department permissions decide which ones a user sees *in
# Personnel* (actions with the personnel_app context); everywhere else every
# department stays readable, as in Odoo. Creating, editing and deleting always
# follow Personnel's permissions.
PERSONNEL_READ_SCOPED_MODELS = ('hr.department',)

# Groups whose bank account rule replaces Odoo's "HR Officers see every bank
# account" rule (Personnel's Employees permissions include HR Officer).
PERSONNEL_BANK_RULE_GROUPS = (
    'advanced_hr.group_employee_create_only',
    'advanced_hr.group_employee_edit_own',
    'advanced_hr.group_employee_edit_team',
    'advanced_hr.group_employee_delete_own',
    'advanced_hr.group_employee_edit_all',
    'advanced_hr.group_employee_view_all',
    'advanced_hr.group_employee_delete_all',
    'advanced_hr.group_audit_trail_view',
)


class IrRule(models.Model):
    _inherit = 'ir.rule'

    def _compute_domain_keys(self):
        return super()._compute_domain_keys() + ['personnel_app']

    @api.model
    @tools.ormcache()
    def _personnel_read_rule_ids(self):
        return frozenset(self.env['ir.model.data'].sudo().search([
            ('module', '=', 'advanced_hr'),
            ('model', '=', 'ir.rule'),
        ]).mapped('res_id'))

    def _personnel_bank_rule_applies(self):
        """Personnel users who are HR Officers only through Personnel."""
        user = self.env.user
        if not user.has_group('advanced_hr.group_personnel_user') or user.has_group('hr.group_hr_manager'):
            return False
        return any(user.has_group(xmlid) for xmlid in PERSONNEL_BANK_RULE_GROUPS)

    def _get_rules(self, model_name, mode='read'):
        rules = super()._get_rules(model_name, mode=mode)
        if not rules:
            return rules
        if (mode == 'read' and model_name in PERSONNEL_READ_SCOPED_MODELS
                and not self.env.context.get('personnel_app')):
            personnel_ids = self._personnel_read_rule_ids()
            rules = rules.filtered(lambda rule: rule.id not in personnel_ids)
        elif model_name == 'res.partner.bank' and self._personnel_bank_rule_applies():
            odoo_rule = self.env.ref('hr.ir_rule_res_partner_bank_employees', raise_if_not_found=False)
            if odoo_rule:
                rules -= odoo_rule
        return rules

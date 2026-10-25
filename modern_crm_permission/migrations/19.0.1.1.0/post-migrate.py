"""Contracts moved out of the CRM: reword the standard roles' descriptions,
unless an administrator has already changed them (roles are noupdate)."""
from odoo import SUPERUSER_ID, api

DESCRIPTIONS = {
    'modern_crm_permission.role_modern_crm_admin': (
        'Everything in the CRM: create, edit and delete any lead, opportunity or contract, every workflow '
        'action (quotes, sales orders, invoices, sending and activating contracts) and Configuration.',
        'Everything in the CRM: create, edit and delete any lead or opportunity, every workflow action '
        '(quotes, sales orders, invoices) and Configuration.'),
    'modern_crm_permission.role_modern_crm_manager': (
        "Create, view and edit their own and their team's leads, opportunities and contracts. No deleting.",
        "Create, view and edit their own and their team's leads and opportunities. No deleting."),
    'modern_crm_permission.role_modern_crm_employee': (
        'Create, view and edit their own leads, opportunities and contracts (created by them or owned by '
        'them). No deleting.',
        'Create, view and edit their own leads and opportunities (created by them or owned by them). '
        'No deleting.'),
    'modern_crm_permission.role_modern_crm_sales_rep': (
        'Work their own leads, opportunities and contracts, create quotes from opportunities and send '
        'contracts for signature. No deleting.',
        'Work their own leads and opportunities and create quotes from opportunities. No deleting.'),
    'modern_crm_permission.role_modern_crm_sales_ops': (
        'View every lead, create and edit every opportunity and contract, activate contracts, confirm sales '
        'orders and create invoices. No deleting.',
        'View every lead, create and edit every opportunity, confirm sales orders and create invoices. '
        'No deleting.'),
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, (old, new) in DESCRIPTIONS.items():
        role = env.ref(xmlid, raise_if_not_found=False)
        if role and role.description == old:
            role.description = new

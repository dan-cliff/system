"""Subscriptions came to Accounting: add their permissions to the standard
roles (noupdate data, so not reloaded). A role an admin deleted is left alone,
and a permission already on a role is not added twice."""
from odoo import SUPERUSER_ID, api

ROLE_PERMISSIONS = {
    'role_accounting_admin': ['create_only', 'edit_own', 'edit_team', 'edit_all', 'view_all', 'delete_own',
                              'delete_all', 'manage', 'invoice'],
    'role_accounting_manager': ['edit_team'],
    'role_accounting_employee': ['edit_own'],
    'role_accounting_approver': ['view_all', 'manage', 'invoice'],
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for role_xmlid, permissions in ROLE_PERMISSIONS.items():
        role = env.ref(f'advanced_accounting_permission.{role_xmlid}', raise_if_not_found=False)
        if not role:
            continue
        present = role.line_ids.mapped('group_id')
        lines = []
        for permission in permissions:
            group = env.ref(f'advanced_accounting.group_subscription_{permission}')
            if group not in present:
                lines.append((0, 0, {'privilege_id': group.privilege_id.id, 'group_id': group.id}))
        if lines:
            role.write({'line_ids': lines})

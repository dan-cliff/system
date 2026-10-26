"""Contracts moved out of the CRM, so their privileges and groups are removed
on this update. Permission Management's role lines require a privilege and a
group (ondelete restrict): drop the lines that point at the contract ones
first, or Odoo could not delete them."""
from odoo.tools import sql


def migrate(cr, version):
    if not sql.table_exists(cr, 'permission_role_line'):
        return
    cr.execute("""
        DELETE FROM permission_role_line
         WHERE privilege_id IN (SELECT res_id FROM ir_model_data
                                 WHERE module = 'modern_crm' AND model = 'res.groups.privilege'
                                   AND name LIKE 'privilege\\_modern\\_crm\\_contract\\_%%')
            OR group_id IN (SELECT res_id FROM ir_model_data
                             WHERE module = 'modern_crm' AND model = 'res.groups'
                               AND name LIKE 'group\\_modern\\_crm\\_contract\\_%%')
    """)

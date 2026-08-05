from odoo import fields, models


class PermissionRoleLine(models.Model):
    _name = 'permission.role.line'
    _description = 'Permission Role Privilege Line'
    _order = 'privilege_id'

    role_id = fields.Many2one(
        comodel_name='permission.role',
        required=True,
        ondelete='cascade',
        index=True,
    )
    privilege_id = fields.Many2one(
        comodel_name='res.groups.privilege',
        string='Privilege',
        required=True,
    )
    group_id = fields.Many2one(
        comodel_name='res.groups',
        string='Access Level',
        required=True,
        domain="[('privilege_id', '=', privilege_id)]",
    )

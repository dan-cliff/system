from odoo import fields, models


class HrJob(models.Model):
    _inherit = 'hr.job'

    default_permission_profile_id = fields.Many2one(
        comodel_name='permission.profile',
        string='Default Permission Profile',
        ondelete='set null',
    )

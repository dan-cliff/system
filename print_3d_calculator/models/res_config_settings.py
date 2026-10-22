from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    print3d_profile_id = fields.Many2one(
        'print3d.pricing.profile',
        string='Default 3D Print Pricing Profile',
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    print3d_profile_id = fields.Many2one(
        related='company_id.print3d_profile_id',
        readonly=False,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    print3d_max_upload_mb = fields.Integer(
        string='Website Upload Limit (MB)',
        config_parameter='print_3d_calculator.max_upload_mb',
        default=100,
    )

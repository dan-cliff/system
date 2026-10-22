# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .embroidery_submission import DEFAULT_STITCHES_PER_MINUTE, STITCHES_PER_MINUTE_PARAM


class ResCompany(models.Model):
    _inherit = 'res.company'

    embroidery_profile_id = fields.Many2one('embroidery.pricing.profile',
                                            string='Default Embroidery Pricing Profile')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    embroidery_submission_spm = fields.Integer(
        string='Estimate duration based on stitches',
        config_parameter=STITCHES_PER_MINUTE_PARAM,
        default=DEFAULT_STITCHES_PER_MINUTE,
        help='Stitches per minute used to estimate how long a submitted design takes to stitch.',
    )
    embroidery_profile_id = fields.Many2one(
        related='company_id.embroidery_profile_id',
        readonly=False,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    embroidery_max_upload_mb = fields.Integer(
        string='Website Upload Limit (MB)',
        config_parameter='embroidery_submission.max_upload_mb',
        default=10,
    )

    @api.constrains('embroidery_submission_spm', 'embroidery_max_upload_mb')
    def _check_embroidery_submission_defaults(self):
        for settings in self:
            if settings.embroidery_submission_spm < 1:
                raise ValidationError(_('"Estimate duration based on stitches" must be at least 1 stitch per minute.'))
            if settings.embroidery_max_upload_mb < 1:
                raise ValidationError(_('The website upload limit must be at least 1 MB.'))

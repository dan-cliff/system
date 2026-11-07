# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .laser_template import (
    DEFAULT_MAX_UPLOAD_MB, MAX_UPLOAD_PARAM, VISUAL_EDITOR_INTERNAL_PARAM, VISUAL_EDITOR_PORTAL_PARAM,
)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    laser_visual_editor_internal = fields.Boolean(
        string='Visual Editor for Employees',
        config_parameter=VISUAL_EDITOR_INTERNAL_PARAM,
        help='Employees place a template\'s variable elements by dragging them on the design, and see '
             'a live preview while they personalise a job.',
    )
    laser_visual_editor_portal = fields.Boolean(
        string='Visual Editor for Customers',
        config_parameter=VISUAL_EDITOR_PORTAL_PARAM,
        help='Customers see their text and pictures on the design as they type, on the product page '
             'of the eCommerce shop. Without it they fill in a form and ask for a preview.',
    )
    laser_max_upload_mb = fields.Integer(
        string='Upload Limit (MB)',
        config_parameter=MAX_UPLOAD_PARAM,
        default=DEFAULT_MAX_UPLOAD_MB,
        help='Largest picture or artwork file that can be uploaded for a job.',
    )
    laser_website_installed = fields.Boolean(compute='_compute_laser_website_installed')

    def _compute_laser_website_installed(self):
        installed = 'website_sale' in self.env['ir.module.module']._installed()
        for settings in self:
            settings.laser_website_installed = installed

    @api.constrains('laser_max_upload_mb')
    def _check_laser_max_upload(self):
        for settings in self:
            if settings.laser_max_upload_mb < 1:
                raise ValidationError(_('The laser upload limit must be at least 1 MB.'))

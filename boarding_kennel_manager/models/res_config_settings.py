from odoo import api, fields, models

INVOICING_APPS = ('account', 'stock')
INVOICING_MODULE = 'boarding_kennel_manager_invoicing'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kennel_observation_times = fields.Char(related='company_id.kennel_observation_times', readonly=False)
    kennel_invoicing = fields.Boolean(related='company_id.kennel_invoicing', readonly=False)
    kennel_invoicing_available = fields.Boolean(compute='_compute_kennel_invoicing_available')

    kennel_cp_theme = fields.Selection(related='company_id.kennel_cp_theme', readonly=False)
    kennel_cp_background = fields.Selection(related='company_id.kennel_cp_background', readonly=False)
    kennel_cp_background_image = fields.Image(related='company_id.kennel_cp_background_image', readonly=False)
    kennel_cp_image_transparency = fields.Integer(related='company_id.kennel_cp_image_transparency', readonly=False)
    kennel_cp_colour_light = fields.Char(related='company_id.kennel_cp_colour_light', readonly=False)
    kennel_cp_colour_dark = fields.Char(related='company_id.kennel_cp_colour_dark', readonly=False)
    kennel_cp_company_logo = fields.Binary(related='company_id.logo', string='Company Logo')

    @api.depends('company_id')
    def _compute_kennel_invoicing_available(self):
        installed = self.env['ir.module.module'].sudo().search_count(
            [('name', 'in', INVOICING_APPS), ('state', '=', 'installed')])
        for settings in self:
            settings.kennel_invoicing_available = installed == len(INVOICING_APPS)

    def set_values(self):
        super().set_values()
        # Normally installed automatically with Accounting and Inventory; make sure of it when switched on.
        if self.kennel_invoicing and self.kennel_invoicing_available:
            module = self.env['ir.module.module'].sudo().search([('name', '=', INVOICING_MODULE)])
            if module and module.state != 'installed':
                module.button_immediate_install()

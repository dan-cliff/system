from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import print_file_parser


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    print3d_dynamic_pricing = fields.Boolean(
        string='3D Print Dynamic Pricing',
        help='The price is worked out from a 3D print file: customers upload their '
             'file on the website, and sales lines take the price of the attached estimate.',
    )
    print3d_profile_id = fields.Many2one(
        'print3d.pricing.profile',
        string='Pricing Profile',
        help='Pricing used for this product. Leave empty to use the company default.',
    )
    print3d_file = fields.Binary(
        string='3D Print File',
        attachment=True,
        copy=False,
        help='Sliced file (G-code, 3MF, ...) or model (STL, OBJ, ...) for this product. '
             'It is read to work out the filaments, total filament and print time.',
    )
    print3d_filename = fields.Char(string='3D Print File Name', copy=False)
    print3d_estimate_id = fields.Many2one(
        'print3d.estimate',
        string='3D Print Estimate',
        copy=False,
        readonly=True,
    )
    print3d_state = fields.Selection(related='print3d_estimate_id.state', string='Analysis Status')
    print3d_error = fields.Text(related='print3d_estimate_id.error_message', string='Analysis Error')
    print3d_slicer = fields.Char(related='print3d_estimate_id.slicer', string='Slicer')
    print3d_filament_count = fields.Integer(related='print3d_estimate_id.filament_count')
    print3d_total_filament_g = fields.Float(related='print3d_estimate_id.total_filament_g')
    print3d_print_time = fields.Char(related='print3d_estimate_id.print_time_display', string='Print Time')
    print3d_cost_total = fields.Monetary(
        related='print3d_estimate_id.cost_total', string='3D Print Cost',
        currency_field='print3d_currency_id',
    )
    print3d_price = fields.Monetary(
        related='print3d_estimate_id.price', string='3D Print Price',
        currency_field='print3d_currency_id',
    )
    print3d_currency_id = fields.Many2one(related='print3d_estimate_id.currency_id', string='3D Print Currency')
    print3d_line_ids = fields.One2many(related='print3d_estimate_id.line_ids', string='3D Print Filaments')

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates.filtered('print3d_file')._print3d_sync_estimate()
        return templates

    def write(self, vals):
        res = super().write(vals)
        if {'print3d_file', 'print3d_filename', 'print3d_profile_id'} & set(vals):
            self._print3d_sync_estimate()
        return res

    def _print3d_sync_estimate(self):
        for template in self:
            estimate = template.print3d_estimate_id
            if not template.print3d_file:
                if estimate and not estimate.locked:
                    estimate.unlink()
                continue
            values = {
                'file': template.with_context(bin_size=False).print3d_file,
                'filename': template.print3d_filename,
                'product_id': template.product_variant_id.id,
                'product_tmpl_id': template.id,
                'company_id': (template.company_id or self.env.company).id,
                'source': 'product',
            }
            if template.print3d_profile_id:
                values['profile_id'] = template.print3d_profile_id.id
            if estimate and not estimate.locked:
                estimate.write(values)
            else:
                template.print3d_estimate_id = self.env['print3d.estimate'].create(values)

    # ── Website helpers (used by the quote widget) ───────────────────────

    @api.model
    def _print3d_website_materials(self):
        return self.env['print3d.material'].sudo().search([('website_published', '=', True)])

    @api.model
    def _print3d_accepted_extensions(self):
        return ','.join(print_file_parser.SUPPORTED_EXTENSIONS)

    @api.model
    def _print3d_max_upload_mb(self):
        value = self.env['ir.config_parameter'].sudo().get_param('print_3d_calculator.max_upload_mb')
        try:
            return max(int(value or 100), 1)
        except ValueError:
            return 100

    def action_print3d_analyse(self):
        self.ensure_one()
        if not self.print3d_estimate_id:
            raise UserError(_('Attach a 3D print file first.'))
        self.print3d_estimate_id.action_analyse()
        return True

    def action_print3d_open_estimate(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'print3d.estimate',
            'res_id': self.print3d_estimate_id.id,
            'view_mode': 'form',
        }

    def action_print3d_set_cost(self):
        for template in self:
            estimate = template.print3d_estimate_id
            if not estimate or estimate.state != 'done':
                raise UserError(_('The 3D print file has not been estimated yet.'))
            cost = estimate.currency_id._convert(
                estimate.cost_total, template.cost_currency_id or template.currency_id,
                estimate.company_id, fields.Date.context_today(template),
            )
            template.standard_price = cost
        return True

    def action_print3d_set_price(self):
        for template in self:
            estimate = template.print3d_estimate_id
            if not estimate or estimate.state != 'done':
                raise UserError(_('The 3D print file has not been estimated yet.'))
            template.list_price = estimate.currency_id._convert(
                estimate.price, template.currency_id, estimate.company_id,
                fields.Date.context_today(template),
            )
        return True

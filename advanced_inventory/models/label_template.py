# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from .design_mixin import LOCATION_TARGETS, TARGETS, target_model

LABEL_DEFAULTS = {
    # 62 x 29 mm: a common label printer roll.
    'product': [
        {'id': 'name', 'type': 'text', 'text': '{{ display_name }}', 'x': 2, 'y': 1.5, 'w': 58, 'h': 7,
         'size': 9, 'bold': True, 'color': '#2A3F8F', 'valign': 'middle'},
        {'id': 'code', 'type': 'text', 'text': '{{ default_code }}', 'x': 2, 'y': 8.5, 'w': 36, 'h': 4,
         'size': 7, 'color': '#5B3DB8'},
        {'id': 'barcode', 'type': 'barcode', 'value': '{{ barcode }}', 'symbology': 'code128',
         'x': 2, 'y': 13, 'w': 40, 'h': 14},
        {'id': 'qr', 'type': 'qr', 'value': '{{ barcode }}', 'x': 45, 'y': 10, 'w': 15, 'h': 15},
    ],
    'location': [
        {'id': 'band', 'type': 'shape', 'x': 0, 'y': 0, 'w': 8, 'h': 29, 'fill': 'company_primary'},
        {'id': 'code', 'type': 'text', 'text': '{{ layout_code }}', 'x': 10, 'y': 1.5, 'w': 30, 'h': 11,
         'size': 22, 'bold': True, 'color': '#2A3F8F'},
        {'id': 'name', 'type': 'text', 'text': '{{ complete_name }}', 'x': 10, 'y': 12.5, 'w': 32, 'h': 5,
         'size': 6, 'color': '#5B3DB8'},
        {'id': 'barcode', 'type': 'barcode', 'value': '{{ barcode }}', 'symbology': 'code128',
         'x': 10, 'y': 18, 'w': 32, 'h': 9},
        {'id': 'qr', 'type': 'qr', 'value': '{{ barcode }}', 'x': 44, 'y': 6, 'w': 17, 'h': 17},
    ],
    'warehouse': [
        {'id': 'band', 'type': 'shape', 'x': 0, 'y': 0, 'w': 62, 'h': 8, 'fill': 'company_primary'},
        {'id': 'logo', 'type': 'image', 'source': 'company_logo', 'x': 2, 'y': 1, 'w': 20, 'h': 6, 'fit': 'contain'},
        {'id': 'name', 'type': 'text', 'text': '{{ name }}', 'x': 2, 'y': 9, 'w': 40, 'h': 8,
         'size': 12, 'bold': True, 'color': '#2A3F8F'},
        {'id': 'barcode', 'type': 'barcode', 'value': '{{ inventory_barcode }}', 'symbology': 'code128',
         'x': 2, 'y': 18, 'w': 40, 'h': 9},
        {'id': 'qr', 'type': 'qr', 'value': '{{ inventory_barcode }}', 'x': 45, 'y': 10, 'w': 15, 'h': 15},
    ],
}


def default_label_layout(target):
    key = 'location' if target in LOCATION_TARGETS else target
    return [dict(element) for element in LABEL_DEFAULTS.get(key, LABEL_DEFAULTS['product'])]


class AdvancedInventoryLabelTemplate(models.Model):
    _name = 'advanced.inventory.label.template'
    _inherit = ['advanced.inventory.design.mixin']
    _description = 'Label Design'
    _design_unit = 'mm'
    _design_size_limits = (10, 450)

    page_width = fields.Float(string='Width (mm)', default=62.0)
    page_height = fields.Float(string='Height (mm)', default=29.0)
    layout = fields.Json(default=lambda self: default_label_layout(self.env.context.get('default_target', 'product')))
    copies = fields.Integer(string='Copies per Record', default=1,
                            help='How many labels to print for each record.')
    report_action_id = fields.Many2one('ir.actions.report', string='Print Action', readonly=True, copy=False)
    paperformat_id = fields.Many2one('report.paperformat', string='Paper Format', readonly=True, copy=False)

    @api.onchange('target')
    def _onchange_target_layout(self):
        # A new design starts from the default layout of what it is for.
        if not self._origin.id:
            self.layout = default_label_layout(self.target)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('layout'):
                vals['layout'] = default_label_layout(vals.get('target', 'product'))
        templates = super().create(vals_list)
        templates._sync_report_action()
        return templates

    def write(self, vals):
        res = super().write(vals)
        if {'name', 'active', 'company_id', 'page_width', 'page_height', 'sequence', 'target'} & set(vals):
            self._sync_report_action()
        return res

    def unlink(self):
        actions = self.sudo().report_action_id
        paperformats = self.sudo().paperformat_id
        res = super().unlink()
        actions.unlink()
        paperformats.unlink()
        return res

    def _sync_report_action(self):
        for template in self.sudo():
            paperformat_vals = {
                'name': 'Label: %s' % template.name,
                'format': 'custom',
                'page_width': max(1, round(template.page_width)),
                'page_height': max(1, round(template.page_height)),
                'orientation': 'Portrait',
                'margin_top': 0, 'margin_bottom': 0, 'margin_left': 0, 'margin_right': 0,
                'header_line': False, 'header_spacing': 0,
                'disable_shrinking': True, 'dpi': 96,
            }
            if template.paperformat_id:
                template.paperformat_id.write(paperformat_vals)
            else:
                template.paperformat_id = self.env['report.paperformat'].sudo().create(paperformat_vals)
            model = target_model(template.target)
            domain = template._design_target_domain()
            action_vals = {
                'name': template.name,
                'model': model,
                'report_type': 'qweb-pdf',
                'report_name': 'advanced_inventory.report_label',
                'report_file': 'advanced_inventory.report_label',
                'paperformat_id': template.paperformat_id.id,
                'print_report_name': "'%s - %%s' %% (object.display_name or '')" % template.name.replace("'", ''),
                'binding_model_id': self.env['ir.model']._get(model).id if template.active else False,
                'binding_type': 'report',
                'domain': repr(domain) if domain else False,
                'inventory_label_template_id': template.id,
            }
            if template.report_action_id:
                template.report_action_id.write(action_vals)
            else:
                template.report_action_id = self.env['ir.actions.report'].sudo().create(action_vals)

    def action_print_preview(self):
        self.ensure_one()
        record = self._design_sample_record()
        if not record:
            raise UserError(self.env._('There is no %s to print yet.', dict(TARGETS)[self.target].lower()))
        return self.report_action_id.report_action(record, config=False)


class ReportInventoryLabel(models.AbstractModel):
    _name = 'report.advanced_inventory.report_label'
    _description = 'Inventory Label Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        # Read the design as superuser; the records are read as the user printing.
        template = self.env['advanced.inventory.label.template'].sudo().browse(
            data.get('inventory_label_template_id')).exists()
        if not template:
            raise UserError(self.env._('This label design no longer exists.'))
        records = self.env[template.target_model].browse(docids)
        if template.target in LOCATION_TARGETS:
            wrong = records.filtered(lambda r: r.storage_level != template.target)
            if wrong:
                raise UserError(self.env._(
                    'The label "%(label)s" is for %(level)s locations. It can\'t be printed for %(names)s.',
                    label=template.name, level=dict(TARGETS)[template.target].lower(),
                    names=', '.join(wrong.mapped('display_name'))))
        pages = []
        for record in records:
            rendered = template._design_render(record)
            pages += [rendered] * max(template.copies, 1)
        return {
            'doc_ids': docids,
            'doc_model': template.target_model,
            'docs': records,
            'template': template,
            'pages': pages,
        }

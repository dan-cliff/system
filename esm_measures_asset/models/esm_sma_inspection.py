# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval


class EsmSmaInspection(models.Model):
    _inherit = 'esm.sma.inspection'
    # The inspection takes its Organisation units from the smoke alarm it inspects.
    _org_parent_field = 'asset_id'

    asset_id = fields.Many2one(
        'asset.asset', string='Smoke Alarm', tracking=True, ondelete='restrict', index=True,
        domain="esm_asset_domain",
        help='Only assets with the Visible Asset Types or Subtypes chosen in '
             'Settings › ESM Measures, and matching the template\'s Asset Filter, are listed.',
    )
    esm_sma_asset_type_ids = fields.Many2many(
        'asset.type', compute='_compute_esm_sma_asset_filter',
    )
    esm_sma_asset_subtype_ids = fields.Many2many(
        'asset.subtype', compute='_compute_esm_sma_asset_filter',
    )
    # Asset options come from the template.
    esm_asset_enabled = fields.Boolean(related='template_id.esm_asset_enabled')
    esm_asset_required = fields.Boolean(related='template_id.esm_asset_required')
    esm_asset_label = fields.Char(compute='_compute_esm_asset_label')
    esm_asset_domain = fields.Char(compute='_compute_esm_sma_asset_filter')

    @api.depends('company_id', 'template_id.esm_asset_domain')
    def _compute_esm_sma_asset_filter(self):
        # The inspection's company decides which asset types are listed.
        for inspection in self:
            company = inspection.company_id or self.env.company
            inspection.esm_sma_asset_type_ids = company.esm_sma_asset_type_ids
            inspection.esm_sma_asset_subtype_ids = company.esm_sma_asset_subtype_ids
            domain = Domain.OR([
                Domain('asset_type_id', 'in', company.esm_sma_asset_type_ids.ids),
                Domain('asset_subtype_id', 'in', company.esm_sma_asset_subtype_ids.ids),
            ])
            template_domain = inspection.template_id.esm_asset_domain
            if template_domain and template_domain.strip() != '[]':
                domain &= Domain(safe_eval(template_domain, {'uid': self.env.uid}))
            inspection.esm_asset_domain = str(list(domain))

    @api.depends('template_id.esm_asset_label')
    def _compute_esm_asset_label(self):
        default = self._fields['asset_id'].get_description(self.env)['string']
        for inspection in self:
            inspection.esm_asset_label = inspection.template_id.esm_asset_label or default

    @api.constrains('asset_id', 'template_id')
    def _check_esm_asset_required(self):
        for inspection in self:
            if inspection.esm_asset_enabled and inspection.esm_asset_required and not inspection.asset_id:
                raise ValidationError(_('%(field)s is required for inspections from the %(template)s template.',
                                        field=inspection.esm_asset_label, template=inspection.template_id.name))

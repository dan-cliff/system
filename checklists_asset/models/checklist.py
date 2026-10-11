# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Checklist(models.Model):
    _inherit = 'checklist.checklist'
    # A checklist for an asset takes its Organisation units from the asset.
    _org_parent_field = 'asset_id'

    asset_id = fields.Many2one(
        'asset.asset', string='Asset', tracking=True, ondelete='restrict', index=True,
    )
    asset_enabled = fields.Boolean(related='template_id.asset_enabled')
    asset_required = fields.Boolean(related='template_id.asset_required')
    asset_label = fields.Char(related='template_id.asset_label')
    # The template's Asset Filter, used as the asset field's domain on the form.
    asset_domain = fields.Char(compute='_compute_asset_domain')

    @api.depends('template_id.asset_domain')
    def _compute_asset_domain(self):
        for checklist in self:
            checklist.asset_domain = checklist.template_id.asset_domain or '[]'

    def _asset_label(self):
        self.ensure_one()
        return self.asset_label or self.env._('Asset')

    @api.onchange('template_id')
    def _onchange_template_id_asset(self):
        if not self.template_id.asset_enabled:
            self.asset_id = False

    @api.constrains('asset_id', 'template_id')
    def _check_asset_required(self):
        for checklist in self:
            template = checklist.template_id
            if template.asset_enabled and template.asset_required and not checklist.asset_id:
                raise ValidationError(self.env._(
                    '%(field)s is required on %(template)s checklists.',
                    field=checklist._asset_label(), template=template.name,
                ))

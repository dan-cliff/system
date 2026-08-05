# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SoapRecipeLine(models.Model):
    _name = 'soap.recipe.line'
    _description = 'Soap Recipe Ingredient Line'
    _order = 'recipe_id, id'

    recipe_id = fields.Many2one(
        'soap.recipe',
        string='Recipe',
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_id = fields.Many2one(
        'product.template',
        string='Oil / Butter / Fat',
        required=True,
        domain=[('is_soap_ingredient', '=', True)],
        ondelete='restrict',
    )
    percentage = fields.Float(
        string='% of Total Oils',
        digits=(5, 2),
        default=0.0,
        help='Percentage of this oil in the total oil weight of the recipe.',
    )

    # ── Computed: weight based on recipe total ─────────────────────────────────
    weight = fields.Float(
        string='Weight (g)',
        digits=(12, 2),
        compute='_compute_weight',
        store=True,
        help='Calculated weight = recipe total oil weight × percentage / 100.',
    )

    # ── Related read-only chemistry display columns ────────────────────────────
    naoh_sap = fields.Float(
        string='NaOH SAP',
        digits=(12, 6),
        related='product_id.soap_naoh_sap',
        readonly=True,
        store=False,
    )
    koh_sap = fields.Float(
        string='KOH SAP',
        digits=(12, 6),
        related='product_id.soap_koh_sap',
        readonly=True,
        store=False,
    )
    soap_iodine = fields.Float(
        string='Iodine',
        digits=(12, 2),
        related='product_id.soap_iodine',
        readonly=True,
        store=False,
    )
    soap_ins = fields.Float(
        string='INS',
        digits=(12, 2),
        related='product_id.soap_ins',
        readonly=True,
        store=False,
    )

    @api.depends('recipe_id.total_oil_weight', 'percentage')
    def _compute_weight(self):
        for line in self:
            line.weight = (line.recipe_id.total_oil_weight or 0.0) * line.percentage / 100.0

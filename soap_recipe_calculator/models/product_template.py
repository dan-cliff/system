# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplateSoap(models.Model):
    """Extend product.template with soap ingredient chemistry fields."""
    _inherit = 'product.template'

    # ── Soap Recipe Link ───────────────────────────────────────────────────────
    soap_recipe_count = fields.Integer(
        string='# Soap Recipes',
        compute='_compute_soap_recipe_count',
    )

    def _compute_soap_recipe_count(self):
        for tmpl in self:
            tmpl.soap_recipe_count = self.env['soap.recipe'].search_count([
                ('product_tmpl_id', '=', tmpl.id),
            ])

    def action_view_soap_recipes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Soap Recipes',
            'res_model': 'soap.recipe',
            'view_mode': 'list,form',
            'domain': [('product_tmpl_id', '=', self.id)],
            'context': {'default_product_tmpl_id': self.id},
        }

    # ── Enable ─────────────────────────────────────────────────────────────────
    is_soap_ingredient = fields.Boolean(
        string='Use as Soap Ingredient',
        default=False,
        help='Mark this product as a soap-making oil, butter, or fat for use in recipes.',
    )

    # ── Saponification Values ───────────────────────────────────────────────────
    soap_naoh_sap = fields.Float(
        string='NaOH SAP Value',
        digits=(12, 6),
        help=(
            'Sodium hydroxide saponification value: grams of NaOH needed to '
            'fully saponify 1 gram of this oil (typical range 0.06–0.21).'
        ),
    )
    soap_koh_sap = fields.Float(
        string='KOH SAP Value',
        digits=(12, 6),
        help=(
            'Potassium hydroxide saponification value: grams of KOH needed to '
            'fully saponify 1 gram of this oil (approx. NaOH SAP × 1.403).'
        ),
    )

    # ── Quality Indicators ──────────────────────────────────────────────────────
    soap_iodine = fields.Float(
        string='Iodine Value',
        digits=(12, 2),
        help=(
            'Iodine value of this oil — measures degree of unsaturation. '
            'Higher = softer bar. Ideal recipe range: 41–70.'
        ),
    )
    soap_ins = fields.Float(
        string='INS Value',
        digits=(12, 2),
        help=(
            'Iodine Number of Saponification (INS = NaOH SAP × 1000 − Iodine). '
            'Ideal recipe range: 136–165; 160 is the commonly cited optimum.'
        ),
    )

    # ── Fatty Acid Profile (%) ──────────────────────────────────────────────────
    soap_fa_lauric = fields.Float(
        string='Lauric Acid (%)',
        digits=(5, 2),
        help='C12:0 saturated. Drives hardness, cleansing, and bubbly lather.',
    )
    soap_fa_myristic = fields.Float(
        string='Myristic Acid (%)',
        digits=(5, 2),
        help='C14:0 saturated. Similar to lauric — hardness, cleansing, and bubbly lather.',
    )
    soap_fa_palmitic = fields.Float(
        string='Palmitic Acid (%)',
        digits=(5, 2),
        help='C16:0 saturated. Contributes to hardness and creamy lather.',
    )
    soap_fa_stearic = fields.Float(
        string='Stearic Acid (%)',
        digits=(5, 2),
        help='C18:0 saturated. Hardness and creamy lather without excessive cleansing.',
    )
    soap_fa_ricinoleic = fields.Float(
        string='Ricinoleic Acid (%)',
        digits=(5, 2),
        help='C18:1 monounsaturated. Unique to castor oil; conditioning and bubbly lather.',
    )
    soap_fa_oleic = fields.Float(
        string='Oleic Acid (%)',
        digits=(5, 2),
        help='C18:1 monounsaturated. Primary conditioning fatty acid; skin-nourishing.',
    )
    soap_fa_linoleic = fields.Float(
        string='Linoleic Acid (%)',
        digits=(5, 2),
        help='C18:2 polyunsaturated (omega-6). Conditioning; high amounts reduce bar life.',
    )
    soap_fa_linolenic = fields.Float(
        string='Linolenic Acid (%)',
        digits=(5, 2),
        help='C18:3 polyunsaturated (omega-3). Conditioning; prone to rancidity at high levels.',
    )

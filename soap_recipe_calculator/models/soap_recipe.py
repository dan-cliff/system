# -*- coding: utf-8 -*-
import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GEMINI_API_URL = (
    'https://generativelanguage.googleapis.com/v1beta/models/'
    'gemini-2.0-flash-lite:generateContent'
)


class SoapRecipe(models.Model):
    _name = 'soap.recipe'
    _description = 'Soap Lye Calculator Recipe'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'name'

    # ── Identity ───────────────────────────────────────────────────────────────
    name = fields.Char(string='Recipe Name', required=True)

    # ── Product Link ───────────────────────────────────────────────────────────
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product',
        index=True,
        domain="[('is_soap_ingredient', '=', True)]",
        help='Optionally link this recipe to a soap ingredient product.',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product Variant',
        index=True,
        domain="[('product_tmpl_id', '=', product_tmpl_id)]",
        help='Optionally link to a specific product variant.',
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
    ], string='Status', default='draft', required=True, copy=False)

    # ── Lye Type ───────────────────────────────────────────────────────────────
    lye_type = fields.Selection([
        ('naoh',  'NaOH — Bar Soap'),
        ('koh',   'KOH — Liquid Soap'),
        ('koh90', 'KOH 90% — Liquid Soap'),
    ], string='Lye Type', default='naoh', required=True,
        help=(
            'NaOH (sodium hydroxide) produces hard bar soap. '
            'KOH (potassium hydroxide) produces liquid/soft soap. '
            'Select KOH 90% if your KOH is only 90% pure.'
        ),
    )

    # ── Recipe Parameters ──────────────────────────────────────────────────────
    total_oil_weight = fields.Float(
        string='Total Oil Weight (g)',
        default=500.0,
        digits=(12, 2),
        help='Total combined weight of all oils/butters in grams.',
    )
    water_pct = fields.Float(
        string='Water (% of Oils)',
        default=38.0,
        digits=(5, 2),
        help='Water as a percentage of total oil weight. Typical range: 33–40%.',
    )
    superfat_pct = fields.Float(
        string='Superfat %',
        default=5.0,
        digits=(5, 2),
        help=(
            'Lye discount: percentage of oils left unsaponified for extra conditioning. '
            'Typical range: 3–10%.'
        ),
    )
    fragrance_pct = fields.Float(
        string='Fragrance (% of Oils)',
        default=3.0,
        digits=(5, 2),
        help='Fragrance or essential oil as a percentage of total oil weight.',
    )

    # ── Ingredients ────────────────────────────────────────────────────────────
    ingredient_ids = fields.One2many(
        'soap.recipe.line',
        'recipe_id',
        string='Ingredients',
    )
    notes = fields.Text(string='Notes')

    # ── Computed: Totals & Amounts ─────────────────────────────────────────────
    total_pct = fields.Float(
        string='Total Oil %',
        digits=(5, 2),
        compute='_compute_all',
        store=True,
        help='Sum of all ingredient percentages. Should equal 100%.',
    )
    lye_amount = fields.Float(
        string='Lye Amount (g)',
        digits=(12, 2),
        compute='_compute_all',
        store=True,
        help='Calculated lye requirement = oil weight × weighted SAP × (1 − superfat%).',
    )
    water_amount = fields.Float(
        string='Water Amount (g)',
        digits=(12, 2),
        compute='_compute_all',
        store=True,
    )
    fragrance_amount = fields.Float(
        string='Fragrance Amount (g)',
        digits=(12, 2),
        compute='_compute_all',
        store=True,
    )

    # ── Computed: Fatty Acid Weighted Averages ─────────────────────────────────
    fa_lauric     = fields.Float(string='Lauric (%)',     digits=(5, 2), compute='_compute_all', store=True)
    fa_myristic   = fields.Float(string='Myristic (%)',   digits=(5, 2), compute='_compute_all', store=True)
    fa_palmitic   = fields.Float(string='Palmitic (%)',   digits=(5, 2), compute='_compute_all', store=True)
    fa_stearic    = fields.Float(string='Stearic (%)',    digits=(5, 2), compute='_compute_all', store=True)
    fa_ricinoleic = fields.Float(string='Ricinoleic (%)', digits=(5, 2), compute='_compute_all', store=True)
    fa_oleic      = fields.Float(string='Oleic (%)',      digits=(5, 2), compute='_compute_all', store=True)
    fa_linoleic   = fields.Float(string='Linoleic (%)',   digits=(5, 2), compute='_compute_all', store=True)
    fa_linolenic  = fields.Float(string='Linolenic (%)',  digits=(5, 2), compute='_compute_all', store=True)

    # ── Computed: Soap Quality Predictions ────────────────────────────────────
    quality_hardness     = fields.Float(string='Hardness',     digits=(5, 2), compute='_compute_all', store=True)
    quality_cleansing    = fields.Float(string='Cleansing',    digits=(5, 2), compute='_compute_all', store=True)
    quality_conditioning = fields.Float(string='Conditioning', digits=(5, 2), compute='_compute_all', store=True)
    quality_bubbly       = fields.Float(string='Bubbly Lather', digits=(5, 2), compute='_compute_all', store=True)
    quality_creamy       = fields.Float(string='Creamy Lather', digits=(5, 2), compute='_compute_all', store=True)
    quality_iodine       = fields.Float(string='Iodine',       digits=(5, 2), compute='_compute_all', store=True)
    quality_ins          = fields.Float(string='INS',          digits=(5, 2), compute='_compute_all', store=True)

    # ── Single compute method (all outputs share the same dependency set) ──────
    @api.depends(
        'lye_type',
        'total_oil_weight',
        'water_pct',
        'superfat_pct',
        'fragrance_pct',
        'ingredient_ids.percentage',
        'ingredient_ids.product_id.soap_naoh_sap',
        'ingredient_ids.product_id.soap_koh_sap',
        'ingredient_ids.product_id.soap_iodine',
        'ingredient_ids.product_id.soap_ins',
        'ingredient_ids.product_id.soap_fa_lauric',
        'ingredient_ids.product_id.soap_fa_myristic',
        'ingredient_ids.product_id.soap_fa_palmitic',
        'ingredient_ids.product_id.soap_fa_stearic',
        'ingredient_ids.product_id.soap_fa_ricinoleic',
        'ingredient_ids.product_id.soap_fa_oleic',
        'ingredient_ids.product_id.soap_fa_linoleic',
        'ingredient_ids.product_id.soap_fa_linolenic',
    )
    def _compute_all(self):
        for recipe in self:
            lines = recipe.ingredient_ids
            total_pct = sum(line.percentage for line in lines)
            recipe.total_pct = total_pct

            # ── Amounts ───────────────────────────────────────────────────────
            recipe.water_amount = (recipe.total_oil_weight or 0.0) * recipe.water_pct / 100.0
            recipe.fragrance_amount = (recipe.total_oil_weight or 0.0) * recipe.fragrance_pct / 100.0

            if not total_pct:
                # No ingredients yet — zero out everything
                recipe.lye_amount = 0.0
                recipe.fa_lauric = recipe.fa_myristic = recipe.fa_palmitic = 0.0
                recipe.fa_stearic = recipe.fa_ricinoleic = recipe.fa_oleic = 0.0
                recipe.fa_linoleic = recipe.fa_linolenic = 0.0
                recipe.quality_hardness = recipe.quality_cleansing = 0.0
                recipe.quality_conditioning = recipe.quality_bubbly = 0.0
                recipe.quality_creamy = recipe.quality_iodine = recipe.quality_ins = 0.0
                continue

            # ── Lye calculation ───────────────────────────────────────────────
            # lye_amount = total_oil_weight × sum(weight_fraction_i × sap_i) × (1 − superfat%)
            # We normalise fractions against total_pct so partial recipes still compute.
            lye_type = recipe.lye_type
            lye_sap = 0.0
            for line in lines:
                frac = line.percentage / total_pct  # normalised weight fraction
                p = line.product_id
                if lye_type == 'naoh':
                    sap = p.soap_naoh_sap or 0.0
                elif lye_type == 'koh':
                    sap = p.soap_koh_sap or 0.0
                else:  # koh90 — account for 90% purity
                    raw = p.soap_koh_sap or 0.0
                    sap = raw / 0.90 if raw else 0.0
                lye_sap += frac * sap

            recipe.lye_amount = (
                (recipe.total_oil_weight or 0.0)
                * lye_sap
                * (1.0 - recipe.superfat_pct / 100.0)
            )

            # ── Fatty acid weighted averages ──────────────────────────────────
            # fa_x = sum(pct_i × oil_fa_x_i) / total_pct  →  weighted average %
            def _wt_fa(attr):
                return sum(
                    line.percentage * (getattr(line.product_id, attr) or 0.0)
                    for line in lines
                ) / total_pct

            recipe.fa_lauric     = _wt_fa('soap_fa_lauric')
            recipe.fa_myristic   = _wt_fa('soap_fa_myristic')
            recipe.fa_palmitic   = _wt_fa('soap_fa_palmitic')
            recipe.fa_stearic    = _wt_fa('soap_fa_stearic')
            recipe.fa_ricinoleic = _wt_fa('soap_fa_ricinoleic')
            recipe.fa_oleic      = _wt_fa('soap_fa_oleic')
            recipe.fa_linoleic   = _wt_fa('soap_fa_linoleic')
            recipe.fa_linolenic  = _wt_fa('soap_fa_linolenic')

            # ── Quality properties ────────────────────────────────────────────
            # Based on soapcalc.net methodology (ranges shown in the view)
            recipe.quality_hardness     = recipe.fa_lauric + recipe.fa_myristic + recipe.fa_palmitic + recipe.fa_stearic
            recipe.quality_cleansing    = recipe.fa_lauric + recipe.fa_myristic
            recipe.quality_conditioning = recipe.fa_ricinoleic + recipe.fa_oleic + recipe.fa_linoleic + recipe.fa_linolenic
            recipe.quality_bubbly       = recipe.fa_lauric + recipe.fa_myristic + recipe.fa_ricinoleic
            recipe.quality_creamy       = recipe.fa_palmitic + recipe.fa_stearic
            recipe.quality_iodine       = _wt_fa('soap_iodine')
            recipe.quality_ins          = _wt_fa('soap_ins')

    # ── State Transitions ──────────────────────────────────────────────────────
    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    # ── AI helpers ────────────────────────────────────────────────────────────
    @staticmethod
    def _raise_gemini_error(resp):
        """Parse a non-OK Gemini API response and raise a clear UserError."""
        try:
            body = resp.json()
            api_msg = body.get('error', {}).get('message', '')
        except Exception:
            api_msg = resp.text or ''

        if resp.status_code == 429:
            # Distinguish quota-zero (billing not enabled) from genuine rate limiting
            if 'limit: 0' in api_msg:
                raise UserError(_(
                    'Your Google API key has a quota limit of 0 — billing has not been '
                    'enabled on the associated Google Cloud project.\n\n'
                    'To fix this:\n'
                    '1. Go to https://console.cloud.google.com/billing and enable billing '
                    'for the project linked to this key, or\n'
                    '2. Create a new key at https://aistudio.google.com/apikey (AI Studio '
                    'keys include a free quota automatically).'
                ))
            raise UserError(_(
                'Gemini API rate limit reached. Please wait a moment and try again.\n\n'
                'Details: %s'
            ) % api_msg)

        if resp.status_code == 404:
            raise UserError(_(
                'Gemini model not found (404). The model may not be available for your API key.\n\n'
                'Details: %s'
            ) % api_msg)

        raise UserError(_('Gemini API error %s: %s') % (resp.status_code, api_msg))

    # ── AI Improvement Suggestions ─────────────────────────────────────────────
    def action_suggest_improvements(self):
        self.ensure_one()

        # Resolve API key: AI app first, then module-level fallback
        params = self.env['ir.config_parameter'].sudo()
        api_key = params.get_param('ai.google_key', default='')
        if not api_key:
            api_key = params.get_param('soap_recipe_calculator.google_api_key', default='')
        if not api_key:
            raise UserError(_(
                'No Google Gemini API key found. '
                'Please add your key under Settings → AI, or under Settings → Soap Recipe Calculator.'
            ))

        prompt = self._build_ai_improvement_prompt()
        system_instruction = (
            'You are an expert soap-making assistant. '
            'Analyse cold-process soap recipes and provide clear, '
            'practical improvement suggestions. '
            'Always respond with valid JSON only — no markdown, no preamble.'
        )

        try:
            resp = requests.post(
                GEMINI_API_URL,
                params={'key': api_key},
                headers={'Content-Type': 'application/json'},
                json={
                    'system_instruction': {
                        'parts': [{'text': system_instruction}],
                    },
                    'contents': [
                        {'parts': [{'text': prompt}]},
                    ],
                    'generationConfig': {
                        'responseMimeType': 'application/json',
                        'temperature': 0.4,
                        'maxOutputTokens': 2000,
                    },
                },
                timeout=60,
            )
            if not resp.ok:
                self._raise_gemini_error(resp)
            raw = resp.json()['candidates'][0]['content']['parts'][0]['text']
            data = json.loads(raw)
        except UserError:
            raise
        except requests.exceptions.Timeout:
            raise UserError(_('The Gemini API request timed out. Please try again.'))
        except requests.exceptions.RequestException as exc:
            raise UserError(_('Gemini API request failed: %s') % exc)
        except (KeyError, json.JSONDecodeError) as exc:
            raise UserError(_('Unexpected response from Gemini API: %s') % exc)

        html = data.get('html_recommendations', '<p>No recommendations returned.</p>')
        changes = json.dumps({
            'ingredient_changes': data.get('ingredient_changes', []),
            'parameter_changes':  data.get('parameter_changes', {}),
        })

        wizard = self.env['soap.recipe.improve.wizard'].create({
            'recipe_id':           self.id,
            'recommendations_html': html,
            'changes_json':        changes,
        })

        return {
            'type':      'ir.actions.act_window',
            'name':      _('AI Improvement Suggestions'),
            'res_model': 'soap.recipe.improve.wizard',
            'res_id':    wizard.id,
            'view_mode': 'form',
            'target':    'new',
        }

    def _build_ai_improvement_prompt(self):
        """Build the prompt sent to the OpenAI API."""
        self.ensure_one()
        lye_label = dict(self._fields['lye_type'].selection).get(self.lye_type, self.lye_type)

        ingredients_lines = []
        for line in self.ingredient_ids:
            p = line.product_id
            ingredients_lines.append(
                f'  - "{p.name}": {line.percentage:.2f}% '
                f'| NaOH SAP {p.soap_naoh_sap} | KOH SAP {p.soap_koh_sap} '
                f'| Lauric {p.soap_fa_lauric}% Myristic {p.soap_fa_myristic}% '
                f'Palmitic {p.soap_fa_palmitic}% Stearic {p.soap_fa_stearic}% '
                f'Ricinoleic {p.soap_fa_ricinoleic}% Oleic {p.soap_fa_oleic}% '
                f'Linoleic {p.soap_fa_linoleic}% Linolenic {p.soap_fa_linolenic}% '
                f'| Iodine {p.soap_iodine} INS {p.soap_ins}'
            )

        quality_lines = [
            f'  - Hardness:     {self.quality_hardness:.1f}  (ideal 29–54)   '
            f'{"IN RANGE" if 29 <= self.quality_hardness <= 54 else "OUT OF RANGE"}',
            f'  - Cleansing:    {self.quality_cleansing:.1f}  (ideal 12–22)   '
            f'{"IN RANGE" if 12 <= self.quality_cleansing <= 22 else "OUT OF RANGE"}',
            f'  - Conditioning: {self.quality_conditioning:.1f}  (ideal 44–69)   '
            f'{"IN RANGE" if 44 <= self.quality_conditioning <= 69 else "OUT OF RANGE"}',
            f'  - Bubbly:       {self.quality_bubbly:.1f}  (ideal 14–46)   '
            f'{"IN RANGE" if 14 <= self.quality_bubbly <= 46 else "OUT OF RANGE"}',
            f'  - Creamy:       {self.quality_creamy:.1f}  (ideal 16–48)   '
            f'{"IN RANGE" if 16 <= self.quality_creamy <= 48 else "OUT OF RANGE"}',
            f'  - Iodine:       {self.quality_iodine:.1f}  (ideal 41–70)   '
            f'{"IN RANGE" if 41 <= self.quality_iodine <= 70 else "OUT OF RANGE"}',
            f'  - INS:          {self.quality_ins:.1f}  (ideal 136–165) '
            f'{"IN RANGE" if 136 <= self.quality_ins <= 165 else "OUT OF RANGE"}',
        ]

        ingredient_names_json = json.dumps([
            line.product_id.name for line in self.ingredient_ids
        ])

        return f"""Analyse this soap recipe and suggest concrete improvements.

RECIPE: {self.name}
Lye type: {lye_label}
Total oil weight: {self.total_oil_weight}g
Water: {self.water_pct}% of oils
Superfat: {self.superfat_pct}%
Oil percentages total: {self.total_pct:.2f}%

INGREDIENTS (name: percentage | chemistry data):
{chr(10).join(ingredients_lines)}

CURRENT QUALITY SCORES:
{chr(10).join(quality_lines)}

Respond with a single JSON object with exactly these fields:

{{
  "html_recommendations": "...",
  "ingredient_changes": [...],
  "parameter_changes": {{...}}
}}

Field details:

"html_recommendations": A rich HTML string (use <h3>, <p>, <ul>, <li>, <strong>, <table>, <tr>, <td>, <th> tags freely; inline styles are fine).
  Include:
  1. A brief overall assessment paragraph.
  2. A quality score summary table with columns: Property | Current | Ideal Range | Status.
  3. A section for each recommended change with the reasoning.
  4. A note on what the recipe already does well.

"ingredient_changes": Array of objects — only include ingredients that actually need a percentage change.
  Each object: {{"product_name": "<exact name>", "current_percentage": <number>, "suggested_percentage": <number>, "reason": "<string>"}}
  Use ONLY these exact ingredient names: {ingredient_names_json}
  IMPORTANT: suggested percentages must sum to 100 (same total as current).

"parameter_changes": Object — only include keys for parameters that actually need changing.
  Allowed keys: "superfat_pct", "water_pct"
  Each value: {{"current": <number>, "suggested": <number>, "reason": "<string>"}}

If a quality score is already in range and no change is needed, omit it from the recommendations.
If no ingredient changes are needed, return an empty array for "ingredient_changes".
If no parameter changes are needed, return an empty object for "parameter_changes".
"""

# -*- coding: utf-8 -*-
import json
import logging

import requests
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

OPENAI_API_URL = 'https://api.openai.com/v1/chat/completions'

QUALITY_RANGES = {
    'hardness':     (29,  54,  'Hardness'),
    'cleansing':    (12,  22,  'Cleansing'),
    'conditioning': (44,  69,  'Conditioning'),
    'bubbly':       (14,  46,  'Bubbly Lather'),
    'creamy':       (16,  48,  'Creamy Lather'),
    'iodine':       (41,  70,  'Iodine'),
    'ins':          (136, 165, 'INS'),
}


class SoapRecipeImproveWizard(models.TransientModel):
    _name = 'soap.recipe.improve.wizard'
    _description = 'Soap Recipe AI Improvement Suggestions'

    recipe_id = fields.Many2one('soap.recipe', required=True, readonly=True)
    recommendations_html = fields.Html(
        string='AI Recommendations',
        readonly=True,
        sanitize=False,
    )
    changes_json = fields.Text(readonly=True)  # hidden — stores parsed change payload

    # ── Save to Chatter ────────────────────────────────────────────────────────
    def action_save_to_chatter(self):
        self.ensure_one()
        self.recipe_id.message_post(
            body=Markup(self.recommendations_html or ''),
            subject=_('AI Recipe Improvement Suggestions'),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        return {'type': 'ir.actions.act_window_close'}

    # ── Accept Recommendations ─────────────────────────────────────────────────
    def action_accept_recommendations(self):
        self.ensure_one()
        recipe = self.recipe_id

        try:
            changes = json.loads(self.changes_json or '{}')
        except (json.JSONDecodeError, TypeError):
            raise UserError(_(
                'Could not parse the recommendation data. '
                'Please use "Save to Chatter" to record the suggestions and apply them manually.'
            ))

        summary_rows = []

        # ── Apply ingredient percentage changes ────────────────────────────────
        for line in recipe.ingredient_ids:
            name_lower = (line.product_id.name or '').lower().strip()
            for change in changes.get('ingredient_changes', []):
                if change.get('product_name', '').lower().strip() == name_lower:
                    old_pct = line.percentage
                    new_pct = float(change.get('suggested_percentage', old_pct))
                    if abs(new_pct - old_pct) > 0.01:
                        summary_rows.append({
                            'label': f'{line.product_id.name} %',
                            'old':   f'{old_pct:.2f}%',
                            'new':   f'{new_pct:.2f}%',
                        })
                        line.percentage = new_pct
                    break

        # ── Apply parameter changes ────────────────────────────────────────────
        for field_name, label in [('superfat_pct', 'Superfat %'), ('water_pct', 'Water %')]:
            entry = changes.get('parameter_changes', {}).get(field_name)
            if entry:
                new_val = float(entry.get('suggested', getattr(recipe, field_name)))
                old_val = getattr(recipe, field_name)
                if abs(new_val - old_val) > 0.01:
                    summary_rows.append({
                        'label': label,
                        'old':   f'{old_val:.2f}%',
                        'new':   f'{new_val:.2f}%',
                    })
                    setattr(recipe, field_name, new_val)

        # ── Post acceptance summary to chatter ─────────────────────────────────
        if summary_rows:
            rows_html = ''.join(
                '<tr>'
                f'<td style="padding:5px 16px 5px 0"><strong>{r["label"]}</strong></td>'
                f'<td style="padding:5px 10px;color:#888;text-decoration:line-through">{r["old"]}</td>'
                f'<td style="padding:5px 0">&#8594; <strong style="color:#28a745">{r["new"]}</strong></td>'
                '</tr>'
                for r in summary_rows
            )
            body = Markup(
                '<p><strong>✅ AI Recommendations Accepted</strong> — '
                'the following changes were applied to the recipe:</p>'
                '<table style="border-collapse:collapse;margin-top:8px">'
                + rows_html +
                '</table>'
            )
        else:
            body = Markup(
                '<p><em>AI recommendations accepted — '
                'the recipe already meets all suggested values; no changes were needed.</em></p>'
            )

        recipe.message_post(
            body=body,
            subject=_('AI Recommendations Accepted'),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        return {'type': 'ir.actions.act_window_close'}

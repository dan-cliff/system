# -*- coding: utf-8 -*-
"""HS Code "Help me": the AI suggests a product's HS code from the user's description."""
import re

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from .hs_ai import ai_available, ai_parse_json, ai_provider_label, ai_research

HS_CODE_RE = re.compile(r'^\d{4}(\.?\d{2})?(\.?\d{2,4})*$')
CONFIDENCE = ('high', 'medium', 'low')

SYSTEM = """You are a customs tariff classification specialist. You classify goods under the
Harmonized System (HS) using the General Rules of Interpretation, section and chapter notes and
the explanatory notes, and you check official sources (the WCO HS nomenclature and the national
customs tariff of the country given) with web searches before answering. You are careful: when the
description leaves the classification open, you say what decides it."""

PROMPT = """Find the most likely HS code for this product.

Product name: {name}
Description from the user (materials, fibre content, ingredients, use, construction):
{description}
{extra}
The business is in {country}. Give the international 6-digit HS code and, when you can find it,
{country}'s national tariff classification (e.g. Australia's 8-digit tariff item and statistical
code) for the same goods.

Search the web for the relevant chapter and heading notes and the national tariff before answering.
Then answer with ONLY a JSON object, no other text:
{{
  "suggestions": [
    {{
      "hs_code": "the 6-digit HS code as dddd.dd",
      "national_code": "{country}'s tariff code for it, or an empty string",
      "title": "the official short description of that code",
      "confidence": "high, medium or low",
      "reasoning": "two or three sentences: why this heading and subheading fit the product"
    }}
  ],
  "questions": ["what about the product would change the classification, if anything"],
  "summary": "one sentence for the user"
}}
List one to three suggestions, the most likely first."""


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    hs_code_ai_available = fields.Boolean(
        compute='_compute_hs_code_ai_available',
        help='An AI key is set (Settings › General Settings › Integrations), so "Help me" can suggest an HS code.')

    def _compute_hs_code_ai_available(self):
        available = ai_available(self.env)
        for product in self:
            product.hs_code_ai_available = available

    def hs_code_ai_info(self):
        """What the "Help me" dialog starts from and how the progress overlay words the AI step."""
        self.ensure_one()
        description = html2plaintext(self.description_sale or self.description or '').strip()
        return {
            'name': self.name or '',
            'description': description,
            'hs_code': self.hs_code or '',
            'provider': ai_provider_label(self.env),
            'country': (self.company_id or self.env.company).country_id.name or self.env._('Australia'),
        }

    def action_hs_code_ai_suggest(self, description):
        """Ask the AI (with web search) for the product's likely HS codes."""
        self.ensure_one()
        description = (description or '').strip()
        if len(description) < 10:
            raise UserError(self.env._(
                'Describe the product a little more: what it is made of (fibre content, materials or '
                'ingredients), what it is for and how it is made.'))
        info = self.hs_code_ai_info()
        extra = ''
        if self.categ_id:
            extra += 'Product category: %s\n' % self.categ_id.complete_name
        if self.hs_code:
            extra += 'HS code currently on the product: %s\n' % self.hs_code
        prompt = PROMPT.format(name=info['name'], description=description, extra=extra, country=info['country'])
        result = ai_research(self.env, prompt, system=SYSTEM, max_tokens=6000)
        data = ai_parse_json(result['text'])
        if isinstance(data, dict) and 'suggestions' not in data:
            data = None
        if not isinstance(data, dict):
            # The answer may start with prose before the JSON.
            text = result['text'] or ''
            start = text.find('{"suggestions"')
            start = start if start >= 0 else text.find('{\n  "suggestions"')
            data = ai_parse_json(text[start:]) if start >= 0 else None
        if not isinstance(data, dict) or not isinstance(data.get('suggestions'), list):
            raise UserError(self.env._('The AI\'s answer could not be understood. Please try again.'))
        suggestions = []
        for item in data['suggestions'][:3]:
            if not isinstance(item, dict):
                continue
            code = self._hs_code_clean(item.get('hs_code'))
            if not code:
                continue
            national = self._hs_code_clean(item.get('national_code'), national=True)
            confidence = str(item.get('confidence') or '').lower()
            suggestions.append({
                'hs_code': code,
                'national_code': national or '',
                'title': str(item.get('title') or '').strip(),
                'confidence': confidence if confidence in CONFIDENCE else 'low',
                'reasoning': str(item.get('reasoning') or '').strip(),
            })
        if not suggestions:
            raise UserError(self.env._('The AI did not find an HS code for this description. Add more detail and try again.'))
        sources = [{'url': url, 'title': result['found'].get(url, url)} for url in result['cited'][:6]]
        if not sources:
            sources = [{'url': url, 'title': title} for url, title in list(result['found'].items())[:6]]
        return {
            'suggestions': suggestions,
            'questions': [str(q).strip() for q in (data.get('questions') or []) if str(q).strip()][:4],
            'summary': str(data.get('summary') or '').strip(),
            'sources': sources,
            'searched': result['searched'],
            'country': info['country'],
        }

    @api.model
    def _hs_code_clean(self, value, national=False):
        """A tidy HS code (digits and dots), or '' when it isn't one. National codes keep
        their local format (e.g. Australia's "6110.30.00 / 11")."""
        if national:
            value = re.sub(r'[^\d./ ]', '', str(value or '')).strip(' ./')
            return value if len(re.sub(r'\D', '', value)) >= 6 else ''
        value = re.sub(r'[^\d.]', '', str(value or '')).strip('.')
        if not value or not HS_CODE_RE.match(value):
            return ''
        digits = value.replace('.', '')
        if len(digits) >= 6:
            return '%s.%s' % (digits[:4], digits[4:6])
        return value


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def hs_code_ai_info(self):
        return self.product_tmpl_id.hs_code_ai_info()

    def action_hs_code_ai_suggest(self, description):
        return self.product_tmpl_id.action_hs_code_ai_suggest(description)

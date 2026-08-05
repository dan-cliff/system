# -*- coding: utf-8 -*-
import json
import logging
import re

import requests

from markupsafe import Markup, escape

from odoo import fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_GEMINI_BASE = 'https://generativelanguage.googleapis.com'

YOUTUBE_CATEGORIES = [
    ('2', 'Autos & Vehicles'),
    ('10', 'Music'),
    ('15', 'Pets & Animals'),
    ('17', 'Sports'),
    ('19', 'Travel & Events'),
    ('20', 'Gaming'),
    ('22', 'People & Blogs'),
    ('23', 'Comedy'),
    ('24', 'Entertainment'),
    ('25', 'News & Politics'),
    ('26', 'Howto & Style'),
    ('27', 'Education'),
    ('28', 'Science & Technology'),
    ('29', 'Nonprofits & Activism'),
]


class VideoMetadataSeoWizard(models.TransientModel):
    _name = 'video.metadata.seo.wizard'
    _description = 'YouTube SEO Improvement Suggestions'

    metadata_id = fields.Many2one(
        'video.metadata',
        string='Metadata Record',
        required=True,
        ondelete='cascade',
    )
    state = fields.Selection(
        [('generating', 'Generating'), ('done', 'Done')],
        default='generating',
        required=True,
    )

    # ── Suggested fields ──────────────────────────────────────────────────
    suggested_title = fields.Char(string='Suggested Title', size=100)
    suggested_description = fields.Text(string='Suggested Description')
    suggested_tags = fields.Char(string='Suggested Tags')
    suggested_category = fields.Selection(YOUTUBE_CATEGORIES, string='Suggested Category')
    rationale_html = fields.Html(string='Rationale', sanitize=False)

    # ── Gemini payload ────────────────────────────────────────────────────
    def _build_seo_payload(self):
        """Build the Gemini request payload for SEO improvement analysis."""
        meta = self.metadata_id
        category_list = '\n'.join(
            f'  {code}: {label}' for code, label in YOUTUBE_CATEGORIES
        )
        current_category_label = dict(YOUTUBE_CATEGORIES).get(
            meta.youtube_category or '27', 'Education'
        )

        parts = []
        title_len = len(meta.youtube_title or '')
        optimal = 'within' if meta.youtube_title and 40 <= title_len <= 70 else 'outside'
        parts.append(
            f'Current YouTube Title ({title_len} chars, {optimal} optimal 40-70 char range): '
            f'{meta.youtube_title or "(none)"}'
        )

        if meta.youtube_description:
            desc_len = len(meta.youtube_description)
            clean = re.sub(r'\s+', ' ', meta.youtube_description).strip()
            parts.append(
                f'Current Description ({desc_len} chars, ideal ≥ 250): '
                f'{clean[:300]}{"..." if desc_len > 300 else ""}'
            )
        else:
            parts.append('Current Description: (none — missing, worth 20 SEO points)')

        if meta.youtube_tags:
            tag_list = [t.strip() for t in meta.youtube_tags.split(',') if t.strip()]
            parts.append(
                f'Current Tags ({len(tag_list)} tags, ideal ≥ 5): {meta.youtube_tags}'
            )
        else:
            parts.append('Current Tags: (none — missing, worth up to 15 SEO points)')

        parts.append(
            f'Current Category: {current_category_label} (ID: {meta.youtube_category or "27"})'
        )
        parts.append(
            f'Thumbnail: {"Uploaded" if meta.thumbnail_image else "Missing — worth 15 SEO points"}'
        )
        parts.append(
            f'Chapter Timestamps: {"Present" if meta.chapter_timestamps else "Missing — worth 5 SEO points"}'
        )
        parts.append(f'Current SEO Score: {meta.seo_score}/100')

        # Add production context if available
        if meta.production_id:
            prod = meta.production_id
            parts.append(f'\nProduction Title: {prod.name}')
            if prod.description:
                clean_desc = re.sub(r'<[^>]+>', ' ', prod.description)
                clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
                if clean_desc:
                    parts.append(f'Production Brief: {clean_desc[:300]}')
            if prod.idea_id:
                idea = prod.idea_id
                if idea.niche:
                    parts.append(f'Niche: {idea.niche}')
                if idea.target_audience:
                    parts.append(f'Target Audience: {idea.target_audience}')
                if idea.keywords:
                    parts.append(f'Keywords: {idea.keywords}')

        current_metadata = '\n'.join(parts)

        system_instruction = (
            'You are an expert YouTube SEO strategist. Analyse the current YouTube metadata for a video '
            'and provide specific, actionable improvements to maximise the SEO score.\n\n'
            'SEO scoring breakdown:\n'
            '- Title present: +20 pts. Title 40-70 chars: +10 pts\n'
            '- Description present: +20 pts. Description ≥ 250 chars: +10 pts\n'
            '- 5+ tags: +15 pts. 2-4 tags: +8 pts\n'
            '- Thumbnail uploaded: +15 pts\n'
            '- Category set: +5 pts\n'
            '- Chapter timestamps: +5 pts\n\n'
            'Return ONLY a valid JSON object — no prose, no markdown fences — in exactly this structure:\n\n'
            '{\n'
            '  "suggested_title": "Improved YouTube title — max 100 chars, keyword-rich",\n'
            '  "suggested_description": "Full improved description in plain text with line breaks. '
            'Hook in first 125 chars. Aim for 300-500 words.",\n'
            '  "suggested_tags": "tag1, tag2, tag3, … (10-15 comma-separated tags, mix broad and specific)",\n'
            f'  "suggested_category": "Best-fit numeric category ID from:\n{category_list}",\n'
            '  "rationale_html": "<p>Summary of changes...</p><ul>'
            '<li><strong>Title:</strong> what changed and why</li>'
            '<li><strong>Description:</strong> what changed and why</li>'
            '<li><strong>Tags:</strong> what changed and why</li>'
            '<li><strong>Category:</strong> what changed and why</li></ul>"\n'
            '}\n\n'
            'IMPORTANT:\n'
            '- suggested_title must be 100 characters or fewer\n'
            '- suggested_category must be exactly one of the numeric IDs listed above\n'
            '- rationale_html must be valid HTML using only <p>, <ul>, <ol>, <li>, <strong>, <em> tags\n'
            '- Be specific about what you changed and exactly why it improves SEO'
        )

        return {
            'contents': [{
                'role': 'user',
                'parts': [{'text': (
                    'Analyse this YouTube metadata and suggest improvements to maximise the SEO score:\n\n'
                    + current_metadata
                )}],
            }],
            'systemInstruction': {'parts': [{'text': system_instruction}]},
            'generationConfig': {'temperature': 0.7, 'maxOutputTokens': 4096},
        }

    # ── Actions ───────────────────────────────────────────────────────────
    def action_generate_seo_suggestions(self):
        """Call Gemini to generate SEO improvements. Returns False to reload the wizard record."""
        self.ensure_one()
        meta = self.metadata_id

        # Reuse shared Gemini infrastructure from the metadata model
        api_key = meta._get_gemini_api_key()
        payload = self._build_seo_payload()
        candidates = meta._candidate_models(api_key)
        if not candidates:
            raise UserError(_('No Gemini models could be found for your API key.'))

        last_error = None
        raw_text = None

        for api_version, model in candidates:
            url = f'{_GEMINI_BASE}/{api_version}/models/{model}:generateContent?key={api_key}'
            _logger.info('Gemini SEO wizard: trying model %s (%s)', model, api_version)
            try:
                resp = requests.post(url, json=payload, timeout=90)
            except requests.exceptions.Timeout:
                raise UserError(_('The Gemini API request timed out. Please try again.'))
            except requests.exceptions.ConnectionError:
                raise UserError(_(
                    'Could not connect to the Gemini API. Check your internet connection.'
                ))

            if resp.status_code == 200:
                data = resp.json()
                try:
                    raw_text = data['candidates'][0]['content']['parts'][0]['text']
                except (KeyError, IndexError):
                    raise UserError(_(
                        'Gemini returned an unexpected response format. Please try again.'
                    ))
                break

            try:
                detail = resp.json().get('error', {}).get('message', resp.text[:300])
            except Exception:
                detail = resp.text[:300]

            if resp.status_code == 404:
                last_error = detail
                continue
            elif resp.status_code == 403:
                raise UserError(_('Gemini API error (403): %s') % detail)
            elif resp.status_code == 429:
                raise UserError(_(
                    'Gemini API rate limit reached. Please wait a moment and try again.'
                ))
            else:
                raise UserError(_('Gemini API error (%s): %s') % (resp.status_code, detail))

        if raw_text is None:
            raise UserError(_(
                'No available Gemini model could be reached.\n\nLast error: %s'
            ) % (last_error or 'Unknown error'))

        # Parse JSON response
        text = raw_text.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[-1]
            if '```' in text:
                text = text.rsplit('```', 1)[0]
        try:
            suggestions = json.loads(text)
        except json.JSONDecodeError as exc:
            _logger.error('Failed to parse Gemini SEO JSON: %s\n%s', exc, raw_text)
            raise UserError(_(
                'Gemini returned a response that could not be parsed. Please try again.'
            ))

        valid_category_ids = {code for code, _ in YOUTUBE_CATEGORIES}
        category = str(suggestions.get('suggested_category', '27')).strip()
        digits = re.search(r'\d+', category)
        category = digits.group(0) if digits else '27'
        if category not in valid_category_ids:
            category = '27'

        self.write({
            'state': 'done',
            'suggested_title': str(suggestions.get('suggested_title', ''))[:100],
            'suggested_description': str(suggestions.get('suggested_description', '')),
            'suggested_tags': str(suggestions.get('suggested_tags', '')),
            'suggested_category': category,
            'rationale_html': str(suggestions.get('rationale_html', '')),
        })
        # Return False so the FormController reloads the record and shows the
        # 'done' state with all suggested fields populated.
        return False

    def action_proceed(self):
        """Apply the AI-suggested improvements to the linked metadata record."""
        self.ensure_one()
        vals = {}
        if self.suggested_title:
            vals['youtube_title'] = self.suggested_title
        if self.suggested_description:
            vals['youtube_description'] = self.suggested_description
        if self.suggested_tags:
            vals['youtube_tags'] = self.suggested_tags
        if self.suggested_category:
            vals['youtube_category'] = self.suggested_category
        if vals:
            self.metadata_id.write(vals)
        return {'type': 'ir.actions.act_window_close'}

    def action_save_to_chatter(self):
        """Post the SEO recommendations as a formatted chatter note on the metadata record."""
        self.ensure_one()
        category_label = dict(YOUTUBE_CATEGORIES).get(self.suggested_category or '', '')

        # Build body as Markup so Odoo does not escape our HTML tags.
        # User-supplied text values are passed through escape() for XSS safety.
        body = Markup('<h3>SEO Improvement Recommendations</h3>')

        if self.suggested_title:
            body += Markup('<p><strong>Suggested Title:</strong> {}</p>').format(
                self.suggested_title
            )
        if self.suggested_description:
            body += Markup(
                '<p><strong>Suggested Description:</strong></p>'
                '<pre style="white-space: pre-wrap; font-family: inherit;">{}</pre>'
            ).format(self.suggested_description)
        if self.suggested_tags:
            body += Markup('<p><strong>Suggested Tags:</strong> {}</p>').format(
                self.suggested_tags
            )
        if category_label:
            body += Markup('<p><strong>Suggested Category:</strong> {}</p>').format(
                escape(category_label)
            )
        if self.rationale_html:
            # rationale_html is already HTML from Gemini — wrap in Markup so it
            # is not double-escaped when concatenated with the rest of the body.
            body += Markup('<hr/><h4>Rationale</h4>') + Markup(self.rationale_html)

        self.metadata_id.message_post(
            body=body,
            subtype_xmlid='mail.mt_note',
        )
        return {'type': 'ir.actions.act_window_close'}

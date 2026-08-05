# -*- coding: utf-8 -*-
import json
import logging
import re

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ── Gemini config ──────────────────────────────────────────────────────────────
_GEMINI_PARAM = 'video_production.gemini_api_key'
_GEMINI_BASE = 'https://generativelanguage.googleapis.com'
_GEMINI_PREFERRED_MODELS = [
    'gemini-2.5-flash',
    'gemini-2.5-flash-preview-05-20',
    'gemini-2.0-flash-lite',
    'gemini-2.0-flash-001',
    'gemini-1.5-flash',
    'gemini-1.5-flash-001',
    'gemini-1.5-flash-8b',
    'gemini-1.5-pro',
    'gemini-1.5-pro-001',
]


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


class VideoMetadata(models.Model):
    _name = 'video.metadata'
    _description = 'YouTube / Video Metadata'
    _inherit = ['mail.thread']
    _order = 'production_id, id'
    _rec_name = 'youtube_title'

    # ── Production Link ───────────────────────────────────────────────────
    production_id = fields.Many2one(
        'video.production',
        string='Production',
        required=True,
        ondelete='cascade',
        tracking=True,
    )

    # ── Thumbnail ─────────────────────────────────────────────────────────
    thumbnail_image = fields.Image(
        string='Thumbnail',
        max_width=1280,
        max_height=720,
        help='YouTube recommended: 1280×720 JPG/PNG, < 2MB.',
    )
    thumbnail_alt_text = fields.Char(
        string='Thumbnail Alt Text / Description',
        help='Describe the thumbnail for accessibility and documentation.',
    )

    # ── YouTube Core Metadata ─────────────────────────────────────────────
    youtube_title = fields.Char(
        string='YouTube Title',
        size=100,
        tracking=True,
        help='Max 100 characters. Appears in YouTube search results.',
    )
    youtube_description = fields.Text(
        string='YouTube Description',
        help='Video description. First 125 chars appear in search results.',
    )
    youtube_tags = fields.Char(
        string='Tags',
        help='Comma-separated list of tags/keywords for YouTube search.',
    )
    youtube_category = fields.Selection(
        YOUTUBE_CATEGORIES,
        string='Category',
        default='27',
    )
    platform_id = fields.Many2one(
        'video.platform',
        string='Platform',
        help='Publishing platform this video is targeted at.',
    )
    channel_id = fields.Many2one(
        'video.platform.channel',
        string='Channel',
        domain="[('platform_id', '=', platform_id)]",
        help='Channel on the selected platform.',
    )
    playlist_id = fields.Many2one(
        'video.platform.playlist',
        string='Playlist',
        domain="['|', ('platform_id', '=', platform_id), ('channel_id', '=', channel_id)]",
        help='Playlist to add this video to.',
    )
    language = fields.Char(
        string='Language',
        default='en',
        help='ISO 639-1 language code (e.g. en, fr, de).',
    )

    # ── Visibility & Settings ─────────────────────────────────────────────
    visibility = fields.Selection(
        [
            ('private', 'Private'),
            ('unlisted', 'Unlisted'),
            ('public', 'Public'),
        ],
        string='Visibility',
        default='private',
        tracking=True,
    )
    made_for_kids = fields.Boolean(
        string='Made for Kids (COPPA)',
        default=False,
        help='Required by YouTube. If your video targets children, set this to True.',
    )
    allow_comments = fields.Boolean(string='Allow Comments', default=True)
    allow_ratings = fields.Boolean(string='Allow Ratings / Likes', default=True)
    age_restricted = fields.Boolean(
        string='Age Restricted',
        default=False,
        help='Mark as age-restricted content on YouTube.',
    )

    # ── Scheduling ────────────────────────────────────────────────────────
    scheduled_publish_dt = fields.Datetime(
        string='Scheduled Publish Date/Time',
        tracking=True,
        help='When set with Private visibility, YouTube will auto-publish at this time.',
    )

    # ── Publishing Info ───────────────────────────────────────────────────
    youtube_url = fields.Char(
        string='YouTube URL',
        readonly=False,
        copy=False,
        tracking=True,
    )
    youtube_video_id = fields.Char(
        string='YouTube Video ID',
        readonly=False,
        copy=False,
        help='The video ID portion of the YouTube URL (e.g. dQw4w9WgXcQ).',
    )
    date_published = fields.Datetime(
        string='Published On',
        readonly=False,
        copy=False,
        tracking=True,
    )

    # ── SEO & Extras ──────────────────────────────────────────────────────
    seo_score = fields.Integer(
        string='SEO Score',
        compute='_compute_seo_score',
        store=True,
        help='Simple SEO score 0-100 based on title, description, tags, and thumbnail completeness.',
    )
    end_screen_notes = fields.Text(
        string='End Screen Notes',
        help='Notes about end screens to configure after publishing.',
    )
    cards_notes = fields.Text(
        string='Cards Notes',
        help='Notes about info cards to add at timestamps.',
    )
    chapter_timestamps = fields.Text(
        string='Chapter Timestamps',
        help='Chapter timestamps to add to description, e.g. 0:00 Intro\n1:30 Main Content.',
    )

    # ── Integration Visibility ────────────────────────────────────────────
    show_social_integration = fields.Boolean(compute='_compute_show_social')

    @api.depends_context('uid')
    def _compute_show_social(self):
        show = (
            self.env['ir.config_parameter'].sudo()
            .get_param('video_production.use_social', 'False') == 'True'
        )
        for rec in self:
            rec.show_social_integration = show

    # ── Social Marketing Integration ──────────────────────────────────────
    # Note: social_post IDs are stored as a text field when social module is
    # not installed. The action below opens social.post if the module is installed.
    social_notes = fields.Text(
        string='Social Media Notes',
        help='Notes about social media posts to create when this video is published.',
    )
    social_post_count = fields.Integer(
        string='Social Posts',
        compute='_compute_social_post_count',
    )

    def _compute_social_post_count(self):
        """Count social posts linked to this production if social module is installed."""
        social_installed = 'social.post' in self.env
        for rec in self:
            if social_installed:
                rec.social_post_count = self.env['social.post'].search_count([
                    ('video_production_id', '=', rec.production_id.id)
                ]) if hasattr(self.env['social.post'], 'video_production_id') else 0
            else:
                rec.social_post_count = 0

    # ── Computed SEO Score ────────────────────────────────────────────────
    @api.depends(
        'youtube_title', 'youtube_description', 'youtube_tags',
        'thumbnail_image', 'youtube_category', 'chapter_timestamps',
    )
    def _compute_seo_score(self):
        for rec in self:
            score = 0
            if rec.youtube_title:
                score += 20
                if 40 <= len(rec.youtube_title) <= 70:
                    score += 10
            if rec.youtube_description:
                score += 20
                if len(rec.youtube_description) >= 250:
                    score += 10
            if rec.youtube_tags:
                tags = [t.strip() for t in rec.youtube_tags.split(',') if t.strip()]
                if len(tags) >= 5:
                    score += 15
                elif len(tags) >= 2:
                    score += 8
            if rec.thumbnail_image:
                score += 15
            if rec.youtube_category:
                score += 5
            if rec.chapter_timestamps:
                score += 5
            rec.seo_score = min(score, 100)

    # ── Gemini helpers ────────────────────────────────────────────────────
    def _get_gemini_api_key(self):
        key = self.env['ir.config_parameter'].sudo().get_param(_GEMINI_PARAM, default='')
        if not key:
            raise UserError(_(
                'A Google Gemini API key has not been configured.\n\n'
                'Please go to:\n'
                'Video Production → Configuration → Settings\n'
                'and enter your Google Gemini API key under the AI section.'
            ))
        return key

    def _list_gemini_models(self, api_key):
        for api_version in ('v1beta', 'v1'):
            url = f'{_GEMINI_BASE}/{api_version}/models?key={api_key}'
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code != 200:
                    continue
                data = resp.json()
            except Exception:
                continue
            available = {
                m.get('name', '').split('/')[-1]
                for m in data.get('models', [])
                if 'generateContent' in m.get('supportedGenerationMethods', [])
            }
            return api_version, available
        return None, set()

    def _candidate_models(self, api_key):
        api_version, available = self._list_gemini_models(api_key)
        if not api_version:
            api_version = 'v1beta'
            available = set()
        seen = []
        for model in _GEMINI_PREFERRED_MODELS:
            if model in available or not available:
                seen.append((api_version, model))
        remaining = available - {m for _, m in seen}
        for model in sorted(
            remaining,
            key=lambda n: (0 if 'flash' in n else 1 if 'pro' in n else 2, n),
        ):
            seen.append((api_version, model))
        return seen

    def _build_metadata_payload(self, prod):
        """Build the Gemini request payload for YouTube metadata suggestions."""
        category_list = '\n'.join(
            f'  {code}: {label}' for code, label in YOUTUBE_CATEGORIES
        )
        context_parts = [f'Video Title: {prod.name}']
        if prod.video_type:
            context_parts.append(f'Content Type: {dict(prod._fields["video_type"].selection).get(prod.video_type, prod.video_type)}')
        if prod.description:
            # Strip HTML tags for cleaner context
            clean_desc = re.sub(r'<[^>]+>', ' ', prod.description or '')
            clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
            if clean_desc:
                context_parts.append(f'Production Brief: {clean_desc}')
        if prod.idea_id:
            idea = prod.idea_id
            if idea.niche:
                context_parts.append(f'Niche / Topic: {idea.niche}')
            if idea.target_audience:
                context_parts.append(f'Target Audience: {idea.target_audience}')
            if idea.keywords:
                context_parts.append(f'Keywords: {idea.keywords}')
        production_context = '\n'.join(context_parts)

        system_instruction = (
            'You are an expert YouTube SEO strategist. Given details about a video production, '
            'generate optimised YouTube metadata.\n\n'
            'Return ONLY a valid JSON object — no prose, no markdown fences — in exactly this structure:\n\n'
            '{\n'
            '  "youtube_title": "Compelling, keyword-rich title — STRICT 100-character maximum",\n'
            '  "youtube_description": "Full YouTube description. Include: hook in first 125 chars, '
            'detailed overview, key talking points, call-to-action, and relevant links placeholder. '
            'Use plain text with line breaks (no HTML). Aim for 300-500 words.",\n'
            '  "youtube_tags": "tag1, tag2, tag3, … (10-15 comma-separated tags, mix broad and specific)",\n'
            f'  "youtube_category": "The numeric category ID from this list that best fits the video:\n{category_list}"\n'
            '}\n\n'
            'IMPORTANT: youtube_title must be 100 characters or fewer. '
            'youtube_category must be exactly one of the numeric IDs listed above.'
        )
        return {
            'contents': [{
                'role': 'user',
                'parts': [{'text': (
                    'Generate optimised YouTube metadata for the following video production:\n\n'
                    + production_context
                )}],
            }],
            'systemInstruction': {'parts': [{'text': system_instruction}]},
            'generationConfig': {'temperature': 0.7, 'maxOutputTokens': 4096},
        }

    def _call_gemini_for_metadata(self, api_key, prod):
        """Call Gemini and return raw text response."""
        payload = self._build_metadata_payload(prod)
        candidates = self._candidate_models(api_key)
        if not candidates:
            raise UserError(_('No Gemini models could be found for your API key.'))

        last_error = None
        for api_version, model in candidates:
            url = f'{_GEMINI_BASE}/{api_version}/models/{model}:generateContent?key={api_key}'
            _logger.info('Gemini metadata: trying model %s (%s)', model, api_version)
            try:
                resp = requests.post(url, json=payload, timeout=60)
            except requests.exceptions.Timeout:
                raise UserError(_('The Gemini API request timed out. Please try again.'))
            except requests.exceptions.ConnectionError:
                raise UserError(_('Could not connect to the Gemini API. Check your internet connection.'))

            if resp.status_code == 200:
                data = resp.json()
                try:
                    return data['candidates'][0]['content']['parts'][0]['text']
                except (KeyError, IndexError):
                    raise UserError(_('Gemini returned an unexpected response format. Please try again.'))

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
                raise UserError(_('Gemini API rate limit reached. Please wait a moment and try again.'))
            else:
                raise UserError(_('Gemini API error (%s): %s') % (resp.status_code, detail))

        raise UserError(_(
            'No available Gemini model could be reached.\n\nLast error: %s'
        ) % (last_error or 'Unknown error'))

    def _parse_metadata_suggestions(self, raw_text):
        """Parse JSON metadata from Gemini response."""
        text = raw_text.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[-1]
            if '```' in text:
                text = text.rsplit('```', 1)[0]
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            _logger.error('Failed to parse Gemini metadata JSON: %s\n%s', e, raw_text)
            raise UserError(_(
                'Gemini returned a response that could not be parsed. Please try again.'
            ))

        valid_category_ids = {code for code, _ in YOUTUBE_CATEGORIES}
        category = str(data.get('youtube_category', '27')).strip()
        # Strip any non-digit prefix/suffix the model may have added
        digits = re.search(r'\d+', category)
        category = digits.group(0) if digits else '27'
        if category not in valid_category_ids:
            category = '27'

        return {
            'youtube_title': str(data.get('youtube_title', ''))[:100],
            'youtube_description': str(data.get('youtube_description', '')),
            'youtube_tags': str(data.get('youtube_tags', '')),
            'youtube_category': category,
        }

    def action_suggest_by_ai(self):
        """Call Gemini to suggest YouTube metadata based on the linked production."""
        self.ensure_one()
        if not self.production_id:
            raise UserError(_('This metadata record must be linked to a production.'))
        api_key = self._get_gemini_api_key()
        raw = self._call_gemini_for_metadata(api_key, self.production_id)
        suggestions = self._parse_metadata_suggestions(raw)
        self.write(suggestions)
        # Return False so the FormController reloads the record and the
        # updated fields are immediately visible in the browser.
        return False

    def action_open_seo_suggest(self):
        """Create an SEO improvement wizard record and open it as a dialog."""
        self.ensure_one()
        wizard = self.env['video.metadata.seo.wizard'].create({'metadata_id': self.id})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'video.metadata.seo.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {},
        }

    # ── Actions ───────────────────────────────────────────────────────────
    def action_create_social_post(self):
        """Open Social Marketing to create a new post linked to this video."""
        self.ensure_one()
        # Check if social module is installed
        if 'social.post' not in self.env:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Social Marketing Not Installed'),
                    'message': _(
                        'Please enable Social Marketing in Video Production settings.'
                    ),
                    'sticky': False,
                    'type': 'warning',
                },
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'social.post',
            'view_mode': 'form',
            'context': {
                'default_message': (
                    f'{self.youtube_title or self.production_id.name}\n\n'
                    f'{self.youtube_url or ""}'
                ),
            },
        }

    def action_view_social_posts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'social.post',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.social_post_ids.ids)],
            'name': _('Social Posts — %s') % self.youtube_title,
        }

    @api.onchange('platform_id')
    def _onchange_platform_id(self):
        """Clear channel and playlist when platform changes."""
        self.channel_id = False
        self.playlist_id = False

    @api.onchange('channel_id')
    def _onchange_channel_id(self):
        """Clear playlist when channel changes."""
        self.playlist_id = False

    @api.onchange('youtube_url')
    def _onchange_youtube_url(self):
        """Auto-extract video ID from URL."""
        if self.youtube_url:
            url = self.youtube_url
            video_id = None
            if 'youtu.be/' in url:
                video_id = url.split('youtu.be/')[-1].split('?')[0]
            elif 'v=' in url:
                video_id = url.split('v=')[-1].split('&')[0]
            if video_id:
                self.youtube_video_id = video_id

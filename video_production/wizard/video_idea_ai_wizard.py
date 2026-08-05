# -*- coding: utf-8 -*-
import json
import logging
import re

import requests

from odoo import fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GEMINI_PARAM = 'video_production.gemini_api_key'
GEMINI_BASE = 'https://generativelanguage.googleapis.com'

# Preferred models in priority order — first one that actually responds is used.
# Older/deprecated models are intentionally excluded even if ListModels lists them.
GEMINI_PREFERRED_MODELS = [
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


class VideoIdeaAIWizard(models.TransientModel):
    _name = 'video.idea.ai.wizard'
    _description = 'Generate Content Ideas with AI'

    idea_prompt = fields.Text(
        string='Idea Prompt',
        required=True,
        help=(
            'Provide a context or search query to run using AI, the resultant '
            'ideas will be added to the Content Ideas list.'
        ),
    )

    # ── API key helper ──────────────────────────────────────────────────────
    def _get_gemini_api_key(self):
        params = self.env['ir.config_parameter'].sudo()
        # Prefer the central AI app settings key (ai.google_key), fall back to
        # the module-specific key stored in video_production.gemini_api_key.
        key = params.get_param('ai.google_key', default='')
        if not key:
            key = params.get_param(GEMINI_PARAM, default='')
        if not key:
            raise UserError(_(
                'A Google Gemini API key has not been configured.\n\n'
                'Please set one in:\n'
                '  • General Settings → AI (recommended), or\n'
                '  • Video Production → Configuration → Settings → AI section.'
            ))
        return key

    # ── Model discovery ─────────────────────────────────────────────────────
    def _list_gemini_models(self, api_key):
        """
        Return (api_version, set_of_model_names) for the first API version
        that responds successfully, or (None, set()) if unreachable.
        """
        for api_version in ('v1beta', 'v1'):
            url = f'{GEMINI_BASE}/{api_version}/models?key={api_key}'
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
            _logger.info(
                'Gemini %s: generateContent-capable models: %s',
                api_version, sorted(available),
            )
            return api_version, available

        return None, set()

    def _candidate_models(self, api_key):
        """
        Return an ordered list of (api_version, model_name) pairs to try.
        Preferred models are tried first; any remaining discovered models follow.
        """
        api_version, available = self._list_gemini_models(api_key)
        if not api_version:
            # Cannot reach ListModels — try preferred list against v1beta blindly
            api_version = 'v1beta'
            available = set()

        seen = []
        # Preferred list first (intersection with discovered, then blind attempts)
        for model in GEMINI_PREFERRED_MODELS:
            if model in available or not available:
                seen.append((api_version, model))

        # Any remaining discovered models not already covered (flash > pro > other)
        remaining = available - {m for _, m in seen}
        for model in sorted(
            remaining,
            key=lambda n: (0 if 'flash' in n else 1 if 'pro' in n else 2, n),
        ):
            seen.append((api_version, model))

        return seen

    # ── Gemini API call ─────────────────────────────────────────────────────
    def _build_payload(self, prompt_text, num_ideas):
        system_instruction = (
            'You are a creative YouTube content strategist. Your task is to generate '
            'video content ideas based on a user\'s prompt or context.\n\n'
            'Return ONLY a valid JSON object — no prose, no markdown fences — in exactly this structure:\n\n'
            '{\n'
            '  "ideas": [\n'
            '    {\n'
            '      "name": "Concise video title — STRICT 50-character maximum. Use a punchy, '
            'searchable title. Do NOT exceed 50 characters under any circumstances.",\n'
            '      "video_type": "tutorial|review|vlog|short|livestream|documentary|other",\n'
            '      "niche": "Topic or niche category (max 50 chars)",\n'
            '      "description": "A rich HTML description of the video concept. Include: '
            'what the video covers, key talking points or sections, why the topic matters '
            'to the audience, and any unique angle or hook. Use <p>, <ul>/<li>, and <b> '
            'tags for structure. Aim for 3-5 sentences or bullet points of detail.",\n'
            '      "target_audience": "Who this video is for (1-2 sentences)",\n'
            '      "keywords": "keyword1\\nkeyword2\\nkeyword3\\nkeyword4\\nkeyword5",\n'
            '      "estimated_duration_min": 10\n'
            '    }\n'
            '  ]\n'
            '}\n\n'
            'IMPORTANT: The "name" field must be 50 characters or fewer. Count carefully.\n'
            f'Generate exactly {num_ideas} ideas. Be creative, specific, and ensure '
            'each idea is actionable and engaging for a YouTube audience.'
        )
        return {
            'contents': [
                {
                    'role': 'user',
                    'parts': [
                        {
                            'text': (
                                f'Generate {num_ideas} YouTube content ideas based on '
                                f'the following context/query:\n\n{prompt_text}'
                            )
                        }
                    ],
                }
            ],
            'systemInstruction': {
                'parts': [{'text': system_instruction}]
            },
            'generationConfig': {
                'temperature': 0.9,
                'maxOutputTokens': 8192,
            },
        }

    def _call_gemini(self, api_key, prompt_text):
        """
        Try each candidate model in order, skipping any that are unavailable
        for this API key (404), until one succeeds.
        """
        number_match = re.search(r'\b(\d+)\s+ideas?\b', prompt_text, re.IGNORECASE)
        num_ideas = int(number_match.group(1)) if number_match else 10
        payload = self._build_payload(prompt_text, num_ideas)

        candidates = self._candidate_models(api_key)
        if not candidates:
            raise UserError(_(
                'No Gemini models could be found for your API key. '
                'Please verify your key at https://aistudio.google.com/apikey'
            ))

        last_error = None
        for api_version, model in candidates:
            url = (
                f'{GEMINI_BASE}/{api_version}/models/{model}'
                f':generateContent?key={api_key}'
            )
            _logger.info('Gemini: trying model %s (%s)', model, api_version)
            try:
                resp = requests.post(url, json=payload, timeout=60)
            except requests.exceptions.Timeout:
                raise UserError(_('The Gemini API request timed out. Please try again.'))
            except requests.exceptions.ConnectionError:
                raise UserError(_(
                    'Could not connect to the Gemini API. '
                    'Please check your internet connection.'
                ))

            if resp.status_code == 200:
                _logger.info('Gemini: success with model %s', model)
                data = resp.json()
                try:
                    return data['candidates'][0]['content']['parts'][0]['text']
                except (KeyError, IndexError):
                    _logger.error('Unexpected Gemini response format: %s', data)
                    raise UserError(_(
                        'Gemini returned an unexpected response format. Please try again.'
                    ))

            # Parse error detail for all non-200 responses
            try:
                detail = resp.json().get('error', {}).get('message', resp.text[:300])
            except Exception:
                detail = resp.text[:300]

            status = resp.status_code
            _logger.warning('Gemini model %s returned %s: %s', model, status, detail)

            if status == 404:
                # This model is not available for this key — try the next one
                last_error = detail
                continue
            elif status == 400:
                raise UserError(_(
                    'Gemini API error (400): %s\n\nPlease check your prompt and API key.'
                ) % detail)
            elif status == 403:
                raise UserError(_(
                    'Gemini API error (403): Access denied.\n\n%s\n\n'
                    'Please check your API key in '
                    'Video Production → Configuration → Settings.'
                ) % detail)
            elif status == 429:
                raise UserError(_(
                    'Gemini API rate limit reached. Please wait a moment and try again.'
                ))
            else:
                raise UserError(_('Gemini API error (%s): %s') % (status, detail))

        raise UserError(_(
            'No available Gemini model could be reached with your API key.\n\n'
            'Last error: %s\n\n'
            'Please verify your key at https://aistudio.google.com/apikey'
        ) % (last_error or 'Unknown error'))

    # ── JSON parser ─────────────────────────────────────────────────────────
    def _parse_ideas(self, raw_text):
        """Parse JSON ideas from the Gemini response."""
        text = raw_text.strip()
        # Strip markdown fences if the model added them anyway
        if text.startswith('```'):
            text = text.split('\n', 1)[-1]
            if '```' in text:
                text = text.rsplit('```', 1)[0]

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            _logger.error(
                'Failed to parse Gemini JSON response: %s\n%s', e, raw_text
            )
            raise UserError(_(
                'Gemini returned a response that could not be parsed. '
                'Please try again. If the problem persists, check the server logs.'
            ))

        # Model may return a bare list or a {"ideas": [...]} wrapper
        if isinstance(data, list):
            ideas = data
        else:
            ideas = data.get('ideas', [])
        if not ideas:
            raise UserError(_(
                'Gemini did not return any content ideas. '
                'Please try a different prompt.'
            ))

        valid_types = {
            'tutorial', 'review', 'vlog', 'short',
            'livestream', 'documentary', 'other',
        }
        normalised = []
        for item in ideas:
            video_type = str(item.get('video_type', 'other')).lower()
            if video_type not in valid_types:
                video_type = 'other'
            duration = item.get('estimated_duration_min', 10)
            try:
                duration = int(duration)
            except (ValueError, TypeError):
                duration = 10
            normalised.append({
                'name': str(item.get('name', 'Untitled Idea'))[:50],
                'video_type': video_type,
                'niche': str(item.get('niche', ''))[:50],
                'description': str(item.get('description', '')),
                'target_audience': str(item.get('target_audience', '')),
                'keywords': str(item.get('keywords', '')),
                'estimated_duration_min': max(1, duration),
            })
        return normalised

    # ── Record creator ──────────────────────────────────────────────────────
    def _create_ideas(self, ideas):
        """Create video.idea records from parsed idea data."""
        Idea = self.env['video.idea']
        created = Idea
        for item in ideas:
            created |= Idea.create({
                'name': item['name'],
                'video_type': item['video_type'],
                'niche': item['niche'],
                'description': item['description'],
                'target_audience': item['target_audience'],
                'keywords': item['keywords'],
                'estimated_duration_min': item['estimated_duration_min'],
                'author_id': self.env.user.id,
            })
        return created

    # ── Main action ─────────────────────────────────────────────────────────
    def action_generate_ideas(self):
        self.ensure_one()
        api_key = self._get_gemini_api_key()
        raw_text = self._call_gemini(api_key, self.idea_prompt)
        ideas = self._parse_ideas(raw_text)
        created = self._create_ideas(ideas)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Ideas Generated!'),
                'message': _(
                    '%d content idea(s) have been added to the Content Ideas list.'
                ) % len(created),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

# -*- coding: utf-8 -*-
import json
import logging
import re
import uuid

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GEMINI_PARAM = 'video_production.gemini_api_key'
GEMINI_BASE = 'https://generativelanguage.googleapis.com'

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


class VideoScript(models.Model):
    _name = 'video.script'
    _description = 'Video Script'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'production_id, version_number desc, id'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────
    name = fields.Char(
        string='Script Name',
        required=True,
        tracking=True,
    )
    production_id = fields.Many2one(
        'video.production',
        string='Production',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    version_number = fields.Integer(
        string='Version',
        default=1,
        readonly=True,
        copy=False,
    )

    # ── Status ────────────────────────────────────────────────────────────
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('in_review', 'In Review'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        copy=False,
    )
    approved_by_id = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        copy=False,
    )
    date_approved = fields.Datetime(
        string='Approved On',
        readonly=True,
        copy=False,
    )

    # ── People ────────────────────────────────────────────────────────────
    author_id = fields.Many2one(
        'res.users',
        string='Author',
        default=lambda self: self.env.user,
        tracking=True,
    )
    reviewer_id = fields.Many2one(
        'res.users',
        string='Reviewer',
    )

    # ── Content ───────────────────────────────────────────────────────────
    outline = fields.Html(
        string='Outline',
        help='High-level structure and talking points.',
    )
    full_script = fields.Html(
        string='Full Script',
        help='Word-for-word script body.',
    )
    notes = fields.Html(
        string='Director / Production Notes',
    )
    estimated_duration_min = fields.Integer(
        string='Est. Duration (min)',
        help='Estimated video length based on this script.',
    )

    # ── Teleprompter ──────────────────────────────────────────────────────
    teleprompter_token = fields.Char(
        string='Teleprompter Token',
        copy=False,
        readonly=True,
        help='Secret token used for the public (IoT display) teleprompter URL.',
    )
    # ── Lifecycle ─────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('teleprompter_token'):
                vals['teleprompter_token'] = uuid.uuid4().hex
        return super().create(vals_list)

    # ── Actions ───────────────────────────────────────────────────────────
    def action_submit_for_review(self):
        for script in self:
            if script.state != 'draft':
                raise UserError(
                    _('Only draft scripts can be submitted for review.')
                )
            script.state = 'in_review'
            if script.reviewer_id:
                script.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=script.reviewer_id.id,
                    note=_('Please review script: %s') % script.name,
                )

    def action_approve(self):
        for script in self:
            if script.state != 'in_review':
                raise UserError(_('Only scripts in review can be approved.'))
            script.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'date_approved': fields.Datetime.now(),
            })

    def action_reject(self):
        for script in self:
            if script.state not in ('in_review', 'approved'):
                raise UserError(_('Only scripts in review or approved can be rejected.'))
            script.state = 'rejected'

    def action_reset_to_draft(self):
        for script in self:
            script.write({
                'state': 'draft',
                'approved_by_id': False,
                'date_approved': False,
            })

    def action_new_version(self):
        """Create a new draft version of this script."""
        self.ensure_one()
        max_version = max(
            self.production_id.script_ids.mapped('version_number') or [0]
        )
        new_script = self.copy({
            'name': _('%s (v%s)') % (
                self.name.split(' (v')[0], max_version + 1
            ),
            'version_number': max_version + 1,
            'state': 'draft',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'video.script',
            'res_id': new_script.id,
            'view_mode': 'form',
        }

    def action_open_teleprompter(self):
        """Open the teleprompter.

        When the IoT app is installed, open the delivery-choice wizard
        (new browser tab or IoT-connected display). Otherwise, skip the
        wizard entirely and just open the teleprompter in a new tab.
        """
        self.ensure_one()
        if 'iot.box' not in self.env:
            return {
                'type': 'ir.actions.act_url',
                'url': '/video/script/%d/teleprompter' % self.id,
                'target': 'new',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Teleprompter'),
            'res_model': 'teleprompter.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_script_id': self.id},
        }

    # ── AI helpers ────────────────────────────────────────────────────────

    def _get_gemini_api_key(self):
        """Return the Gemini API key, preferring the central AI app setting."""
        params = self.env['ir.config_parameter'].sudo()
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

    def _list_gemini_models(self, api_key):
        """Return (api_version, set_of_model_names) for the first responding API version."""
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
        """Return an ordered list of (api_version, model_name) pairs to try."""
        api_version, available = self._list_gemini_models(api_key)
        if not api_version:
            api_version = 'v1beta'
            available = set()
        seen = []
        for model in GEMINI_PREFERRED_MODELS:
            if model in available or not available:
                seen.append((api_version, model))
        remaining = available - {m for _, m in seen}
        for model in sorted(
            remaining,
            key=lambda n: (0 if 'flash' in n else 1 if 'pro' in n else 2, n),
        ):
            seen.append((api_version, model))
        return seen

    def _build_script_payload(self):
        """Build the Gemini API payload for script generation."""
        production = self.production_id

        def strip_html(html_text):
            return re.sub(r'<[^>]+>', ' ', html_text or '').strip()

        video_type_labels = {
            'tutorial': 'Tutorial',
            'review': 'Review',
            'vlog': 'Vlog',
            'short': 'Short / Reel',
            'livestream': 'Live Stream',
            'documentary': 'Documentary',
            'other': 'Other',
        }
        video_type_label = video_type_labels.get(production.video_type or 'other', 'Other')
        prod_description = strip_html(production.description)
        duration_hint = (
            f'Target video length: approximately {self.estimated_duration_min} minutes.\n'
            if self.estimated_duration_min else ''
        )

        # Enrich context from the source idea if available
        idea_context = ''
        if production.idea_id:
            idea = production.idea_id
            if idea.niche:
                idea_context += f'Topic / Niche: {idea.niche}\n'
            if idea.target_audience:
                idea_context += f'Target Audience: {idea.target_audience}\n'
            if idea.keywords:
                idea_context += f'SEO Keywords: {idea.keywords}\n'

        system_instruction = (
            'You are an expert YouTube video scriptwriter and creative director. '
            'Given the details of a video production, generate a complete scripting draft '
            'with three distinct components.\n\n'
            'Return ONLY a valid JSON object — no prose, no markdown fences — in exactly this structure:\n\n'
            '{\n'
            '  "outline": "<HTML string>",\n'
            '  "full_script": "<HTML string>",\n'
            '  "director_notes": "<HTML string>"\n'
            '}\n\n'
            'Requirements for each field:\n\n'
            '"outline":\n'
            '  A clear, structured video outline. Use <h3> for major sections '
            '(e.g. Intro/Hook, Section 1, Section 2, Outro/CTA), '
            '<ul>/<li> for talking points within each section, and <b> for key phrases. '
            'The outline should cover the full arc of the video from opening hook to final call-to-action.\n\n'
            '"full_script":\n'
            '  The complete word-for-word shooting script. Write in a natural, conversational '
            'tone suitable for on-camera delivery. Use <h3> for section headings, <p> for '
            'spoken paragraphs, <b>[STAGE DIRECTION]</b> for camera/action cues, and '
            '<blockquote> for any on-screen text, quotes, or lower-thirds. '
            'Be detailed and specific — this should be ready to read from a teleprompter.\n\n'
            '"director_notes":\n'
            '  High-level production guidance structured with three <h3> sections:\n'
            '  1. "Shot Ideas" — specific camera angles, transitions, b-roll suggestions, '
            'and any special visual techniques worth considering.\n'
            '  2. "Product Placement Opportunities" — natural, non-intrusive ways to feature '
            'products, tools, or branded items that fit the content organically.\n'
            '  3. "Revenue & Sponsorship Ideas" — potential sponsors, affiliate products, '
            'mid-roll ad placement suggestions, merchandise tie-ins, and any monetisation '
            'angles that fit the video\'s niche and audience.\n'
            '  Use <ul>/<li> for each point under each section.\n\n'
            f'{duration_hint}'
        )

        user_message = (
            f'Please generate a complete script draft for the following video production:\n\n'
            f'Production Title: {production.name}\n'
            f'Script Name: {self.name}\n'
            f'Content Type: {video_type_label}\n'
        )
        if prod_description:
            user_message += f'Production Brief: {prod_description}\n'
        if idea_context:
            user_message += idea_context

        return {
            'contents': [
                {
                    'role': 'user',
                    'parts': [{'text': user_message}],
                }
            ],
            'systemInstruction': {
                'parts': [{'text': system_instruction}]
            },
            'generationConfig': {
                'temperature': 0.8,
                'maxOutputTokens': 16384,
            },
        }

    def _call_gemini_for_script(self, api_key):
        """Call the Gemini API and return the raw text response."""
        payload = self._build_script_payload()
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
            _logger.info('Gemini script: trying model %s (%s)', model, api_version)
            try:
                resp = requests.post(url, json=payload, timeout=120)
            except requests.exceptions.Timeout:
                raise UserError(_('The Gemini API request timed out. Please try again.'))
            except requests.exceptions.ConnectionError:
                raise UserError(_(
                    'Could not connect to the Gemini API. '
                    'Please check your internet connection.'
                ))

            if resp.status_code == 200:
                _logger.info('Gemini script: success with model %s', model)
                data = resp.json()
                try:
                    return data['candidates'][0]['content']['parts'][0]['text']
                except (KeyError, IndexError):
                    _logger.error('Unexpected Gemini response format: %s', data)
                    raise UserError(_(
                        'Gemini returned an unexpected response format. Please try again.'
                    ))

            try:
                detail = resp.json().get('error', {}).get('message', resp.text[:300])
            except Exception:
                detail = resp.text[:300]

            status = resp.status_code
            _logger.warning('Gemini script model %s returned %s: %s', model, status, detail)

            if status == 404:
                last_error = detail
                continue
            elif status == 400:
                raise UserError(_(
                    'Gemini API error (400): %s\n\nPlease check your API key.'
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

    def _parse_script_response(self, raw_text):
        """Parse the JSON script response from Gemini."""
        text = raw_text.strip()
        # Strip markdown fences if the model added them
        if text.startswith('```'):
            text = text.split('\n', 1)[-1]
            if '```' in text:
                text = text.rsplit('```', 1)[0]

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            _logger.error('Failed to parse Gemini script JSON: %s\n%s', e, raw_text)
            raise UserError(_(
                'Gemini returned a response that could not be parsed. '
                'Please try again. If the problem persists, check the server logs.'
            ))

        if not isinstance(data, dict):
            raise UserError(_('Gemini returned an unexpected response format. Please try again.'))

        return {
            'outline': data.get('outline', ''),
            'full_script': data.get('full_script', ''),
            'director_notes': data.get('director_notes', ''),
        }

    def action_generate_with_ai(self):
        """Generate outline, full script, and director notes using Gemini AI."""
        self.ensure_one()
        api_key = self._get_gemini_api_key()
        raw_text = self._call_gemini_for_script(api_key)
        data = self._parse_script_response(raw_text)
        self.write({
            'outline': data['outline'] or self.outline,
            'full_script': data['full_script'] or self.full_script,
            'notes': data['director_notes'] or self.notes,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Script Draft Generated!'),
                'message': _(
                    'AI has written an outline, full script, and director notes. '
                    'Review and refine as needed.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }

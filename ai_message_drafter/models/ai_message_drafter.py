"""
AI Message Drafter
==================
Writes chatter messages with AI. Uses the API keys entered under Settings ›
General Settings › Integrations (claude_ai_settings), trying in order:
  1. claude_ai_settings.api_key         → Claude AI
  2. claude_ai_settings.gemini_api_key  → Google Gemini (backup)
"""

import logging
import re
import time

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext, html_sanitize

_logger = logging.getLogger(__name__)

CLAUDE_URL = 'https://api.anthropic.com/v1/messages'
CLAUDE_API_VERSION = '2023-06-01'
CLAUDE_MODEL = 'claude-opus-5-5'
# Retried once: rate limits, overload and server errors.
CLAUDE_ATTEMPTS = 2
RETRY_STATUSES = (429, 500, 502, 503, 504, 529)
GEMINI_MODEL = 'gemini-2.5-flash'
GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent'

# Recent messages of the record given to the AI as context.
HISTORY_LIMIT = 8
HISTORY_MESSAGE_CHARS = 4000

SYSTEM_PROMPT = """\
You draft messages that a user of an Odoo business system sends from a record's \
chatter, either by email to the record's followers or as an internal note.

Write the message the user asks for, ready to send:
- Reply with only the message body as HTML, using p, br, strong, em, u, ul, ol, \
li, a, h3 and h4. No <html>, <head>, <body> or <style> tags, no inline styles, no \
markdown and no code fences.
- No subject line. End with a short sign-off (e.g. "Kind regards,") and the \
sender's name only: their full signature is added automatically.
- Write in the language of the user's request, in a friendly, professional tone, \
unless the request asks for something else.
- Use only facts from the request and the record details. Where the message needs \
a detail you don't have (a date, a price, a name), put a placeholder in square \
brackets, e.g. [delivery date], for the user to fill in.
- Keep it as short as its purpose allows.
"""

HELPDESK_PROMPT = """\
This record is a Helpdesk ticket. Write a reply to the customer that responds to \
the issue in the ticket description, pitches its tone to the customer's sentiment \
(acknowledge frustration or urgency where the sentiment notes show it) and tells \
them what happens next, drawing on the recommended actions. The recommended \
actions and sentiment notes are internal guidance for the support agent: tell the \
customer about the steps that concern them in customer-friendly words, and never \
copy the internal list or mention the sentiment analysis.
"""


class AiMessageDrafter(models.AbstractModel):
    _name = 'ai.message.drafter'
    _description = 'AI Message Drafter'

    # ── Providers ────────────────────────────────────────────────────────

    @api.model
    def _providers(self):
        """[(api key, label, method)] in the order to try them: Claude first."""
        params = self.env['ir.config_parameter'].sudo()
        providers = []
        claude_key = params.get_param('claude_ai_settings.api_key')
        if claude_key:
            providers.append((claude_key, 'Claude', self._generate_claude))
        gemini_key = params.get_param('claude_ai_settings.gemini_api_key')
        if gemini_key:
            providers.append((gemini_key, 'Google Gemini', self._generate_gemini))
        return providers

    @api.model
    def _generate_claude(self, api_key, system, user_prompt):
        """Claude over its HTTP API (no SDK on the server). The server-side
        fallback re-runs the request on another model if this one declines."""
        body = {
            'model': CLAUDE_MODEL,
            'max_tokens': 16000,
            'fallbacks': 'default',
            'output_config': {'effort': 'low'},
            'system': system,
            'messages': [{'role': 'user', 'content': user_prompt}],
        }
        headers = {
            'x-api-key': api_key,
            'anthropic-version': CLAUDE_API_VERSION,
            'anthropic-beta': 'server-side-fallback-2026-07-01',
            'content-type': 'application/json',
        }
        for attempt in range(CLAUDE_ATTEMPTS):
            try:
                response = requests.post(CLAUDE_URL, headers=headers, json=body, timeout=(15, 300))
            except requests.RequestException as error:
                if attempt + 1 < CLAUDE_ATTEMPTS:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise UserError(self.env._('Could not reach Claude: %s', error)) from error
            if response.status_code in RETRY_STATUSES and attempt + 1 < CLAUDE_ATTEMPTS:
                time.sleep(2 * (attempt + 1))
                continue
            break
        if response.status_code >= 400:
            raise UserError(self._claude_error(response))
        try:
            answer = response.json()
        except ValueError as error:
            raise UserError(self.env._('Claude sent an answer that could not be read.')) from error
        if answer.get('stop_reason') == 'refusal':
            raise UserError(self.env._('Claude declined to write this message.'))
        return ''.join(block.get('text', '') for block in answer.get('content', [])
                       if block.get('type') == 'text')

    @api.model
    def _claude_error(self, response):
        if response.status_code == 401:
            return self.env._('Claude rejected the API key.')
        try:
            message = response.json().get('error', {}).get('message') or response.text
        except ValueError:
            message = response.text
        return self.env._('Claude returned an error (%(status)s): %(message)s',
                          status=response.status_code, message=message[:500])

    @api.model
    def _generate_gemini(self, api_key, system, user_prompt):
        try:
            response = requests.post(
                GEMINI_URL % GEMINI_MODEL,
                params={'key': api_key},
                json={
                    'system_instruction': {'parts': [{'text': system}]},
                    'contents': [{'role': 'user', 'parts': [{'text': user_prompt}]}],
                    'generationConfig': {'maxOutputTokens': 16000},
                },
                timeout=300,
            )
            response.raise_for_status()
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        except requests.HTTPError as error:
            raise UserError(self.env._('Google Gemini returned an error (%s).', error.response.status_code)) from error
        except (requests.RequestException, KeyError, IndexError, ValueError) as error:
            raise UserError(self.env._('Could not get an answer from Google Gemini: %s', error)) from error

    # ── Record context ───────────────────────────────────────────────────

    @api.model
    def _get_record(self, res_model, res_id):
        """The record the chatter belongs to, checking the user may read it."""
        if res_model not in self.env or not res_id:
            raise UserError(self.env._('Save the record before drafting a message.'))
        record = self.env[res_model].browse(res_id).exists()
        if not record:
            raise UserError(self.env._('This record no longer exists.'))
        record.check_access('read')
        return record

    @api.model
    def _is_helpdesk_ticket(self, record):
        return record._name == 'helpdesk.ticket' and 'ai_recommended_actions' in record._fields

    @api.model
    def _helpdesk_parts(self, record):
        """[(label, text)] of the ticket's details the AI reads, leaving out empty ones."""
        parts = [
            ('Description', html2plaintext(record.description or '')),
            ('Customer sentiment', record.sentiment_id.name or ''),
            ('Sentiment notes', record.sentiment_reason or ''),
            ('Recommended actions', html2plaintext(record.ai_recommended_actions or '')),
        ]
        return [(label, text.strip()) for label, text in parts if text and text.strip()]

    @api.model
    def _record_context(self, record):
        """The record's details and recent messages, as text for the AI."""
        lines = [
            f'Record: {record.display_name} ({self.env["ir.model"]._get(record._name).name})',
            f'Sender: {self.env.user.name}, {self.env.company.name}',
        ]
        partner = record['partner_id'] if 'partner_id' in record._fields else False
        if partner and partner._name == 'res.partner':
            lines.append(f'Customer / contact: {partner.display_name}')
        if self._is_helpdesk_ticket(record):
            for label, text in self._helpdesk_parts(record):
                lines.append(f'\n{label}:\n{text}')
        messages = self.env['mail.message'].search([
            ('model', '=', record._name),
            ('res_id', '=', record.id),
            ('message_type', 'in', ('email', 'comment')),
        ], order='id desc', limit=HISTORY_LIMIT)
        if messages:
            lines.append('\nRecent messages on the record (newest first):')
            for message in messages:
                kind = 'Internal note' if message.subtype_id.internal else 'Message'
                author = message.author_id.name or message.email_from or 'Unknown'
                text = html2plaintext(message.body or '').strip()[:HISTORY_MESSAGE_CHARS]
                date = fields.Datetime.context_timestamp(self, message.date)
                if text:
                    lines.append(f'- {kind} from {author} '
                                 f'on {date.strftime("%d/%m/%Y %H:%M")}:\n{text}')
        return '\n'.join(lines)

    @api.model
    def get_draft_context(self, res_model, res_id):
        """What the dialog and its progress overlay need to know before asking the AI."""
        record = self._get_record(res_model, res_id)
        helpdesk = self._is_helpdesk_ticket(record)
        return {
            'record_name': record.display_name,
            'providers': [label for _key, label, _method in self._providers()],
            'helpdesk': helpdesk,
            'helpdesk_parts': [label for label, _text in self._helpdesk_parts(record)] if helpdesk else [],
        }

    # ── Drafting ─────────────────────────────────────────────────────────

    @api.model
    def generate_draft(self, res_model, res_id, prompt='', draft='', changes=''):
        """Write a message for the record's chatter with AI.

        :param prompt: what the user wants the message to say
        :param draft: the current draft (HTML) when asking for changes to it
        :param changes: the changes the user wants made to `draft`
        :return: {'body': sanitized HTML, 'provider': label of the AI that wrote it}
        """
        record = self._get_record(res_model, res_id)
        helpdesk = self._is_helpdesk_ticket(record)
        prompt, changes = (prompt or '').strip(), (changes or '').strip()
        if not prompt and not helpdesk:
            raise UserError(self.env._('Describe the message you want.'))
        if draft and not changes:
            raise UserError(self.env._('Describe the changes you want.'))
        providers = self._providers()
        if not providers:
            raise UserError(self.env._(
                'No AI is set up. Add a Claude AI or Google Gemini API key in Settings › '
                'General Settings › Integrations.'))

        system = SYSTEM_PROMPT + ('\n' + HELPDESK_PROMPT if helpdesk else '')
        sections = [self._record_context(record)]
        sections.append(f"The user's request:\n{prompt}" if prompt else
                        'The user gave no instructions: suggest an appropriate reply to the customer.')
        if draft:
            sections.append(f'The current draft (the user may have edited it by hand):\n{draft}')
            sections.append(f'Rewrite the draft with these changes and reply with the whole '
                            f'revised message:\n{changes}')
        user_prompt = '\n\n'.join(sections)

        errors = []
        for api_key, label, generate in providers:
            try:
                body = self._clean_html(generate(api_key, system, user_prompt))
                if body:
                    return {'body': body, 'provider': label}
                errors.append('%s: %s' % (label, self.env._('the answer was empty.')))
            except UserError as error:
                _logger.warning('AI Message Drafter: %s failed: %s', label, error)
                errors.append('%s: %s' % (label, error))
        raise UserError(self.env._('The message could not be written.\n\n%s', '\n'.join(errors)))

    @api.model
    def _clean_html(self, text):
        """The AI's answer as safe HTML for the editor: fences and page wrappers
        removed, plain text turned into paragraphs, then sanitized."""
        text = (text or '').strip()
        text = re.sub(r'^```[a-zA-Z]*\s*|\s*```$', '', text).strip()
        body = re.search(r'<body[^>]*>(.*)</body>', text, re.S | re.I)
        if body:
            text = body.group(1).strip()
        if text and not re.search(r'<(p|div|ul|ol|h\d|br)\b', text, re.I):
            text = ''.join('<p>%s</p>' % paragraph.replace('\n', '<br/>')
                           for paragraph in re.split(r'\n\s*\n', text) if paragraph.strip())
        return html_sanitize(text, strip_style=True) or ''

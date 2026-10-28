"""AI helpers for the Development apps.

Development has no AI credentials of its own. It uses the first key it finds,
preferring Claude/Anthropic and falling back to Google Gemini:

1. Claude AI key in Settings > General Settings > Integrations (claude_ai_settings),
2. Anthropic key of the Odoo AI app (ai / ai_anthropic),
3. Google Gemini key in Settings > General Settings > Integrations,
4. Google key of the Odoo AI app.

Neither AI app is a dependency: when none is installed, or no key is set, every
AI feature is hidden (``dev.ai._available()`` is False), background AI jobs are
skipped and an explicit call raises a friendly UserError.
"""
import json
import logging

import requests

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CLAUDE_API_URL = 'https://api.anthropic.com/v1/messages'
CLAUDE_MODEL = 'claude-sonnet-5-5'
CLAUDE_API_VERSION = '2023-06-01'
# Lets the API retry a declined request on a suitable model instead of failing.
CLAUDE_FALLBACK_BETA = 'server-side-fallback-2026-07-01'
GEMINI_MODEL = 'gemini-2.5-flash'
GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent'

# (provider, system parameter) in order of preference.
KEY_PARAMS = [
    ('claude', 'claude_ai_settings.api_key'),
    ('claude', 'ai.anthropic_key'),
    ('gemini', 'claude_ai_settings.gemini_api_key'),
    ('gemini', 'ai.google_key'),
]
PROVIDER_LABELS = {'claude': 'Claude', 'gemini': 'Gemini'}


def ai_credentials(env):
    """(provider, api key) of the first AI key set, or (None, '') when no AI is set up."""
    params = env['ir.config_parameter'].sudo()
    for provider, param in KEY_PARAMS:
        key = (params.get_param(param) or '').strip()
        if key:
            return provider, key
    return None, ''


def no_ai_message(env):
    return env._('No AI is set up. Add a Claude AI (preferred) or Google Gemini API key in '
             'Settings > General Settings > Integrations, or in the Odoo AI app settings.')


def ai_request_text(env, prompt, system='', max_tokens=4000, timeout=180):
    """Send one prompt to the configured AI and return its answer, raising UserError on failure."""
    provider, api_key = ai_credentials(env)
    if not api_key:
        raise UserError(no_ai_message(env))
    if provider == 'claude':
        return _claude(env, api_key, prompt, system, max_tokens, timeout)
    return _gemini(env, api_key, prompt, system, max_tokens, timeout)


def _error_detail(response, key='error'):
    try:
        return response.json().get(key, {}).get('message') or response.text
    except ValueError:
        return response.text


def _claude(env, api_key, prompt, system, max_tokens, timeout):
    body = {
        'model': CLAUDE_MODEL,
        'max_tokens': max_tokens,
        'messages': [{'role': 'user', 'content': prompt}],
        'fallbacks': 'default',
    }
    if system:
        body['system'] = system
    try:
        response = requests.post(CLAUDE_API_URL, json=body, timeout=timeout, headers={
            'x-api-key': api_key,
            'anthropic-version': CLAUDE_API_VERSION,
            'anthropic-beta': CLAUDE_FALLBACK_BETA,
            'content-type': 'application/json',
        })
    except requests.RequestException as exc:
        _logger.warning('Claude API call failed: %s', exc)
        raise UserError(env._('Could not reach the Claude API: %s', exc)) from exc
    if response.status_code >= 400:
        detail = _error_detail(response)
        _logger.warning('Claude API returned %s: %s', response.status_code, detail)
        raise UserError(env._('Claude API error (%(status)s): %(detail)s', status=response.status_code, detail=detail))
    payload = response.json()
    if payload.get('stop_reason') == 'refusal':
        raise UserError(env._('Claude declined this request. Please review the record and try again.'))
    return ''.join(block.get('text', '') for block in payload.get('content', []) if block.get('type') == 'text')


def _gemini(env, api_key, prompt, system, max_tokens, timeout):
    body = {
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'generationConfig': {'maxOutputTokens': max_tokens},
    }
    if system:
        body['systemInstruction'] = {'parts': [{'text': system}]}
    try:
        response = requests.post(GEMINI_API_URL % GEMINI_MODEL, json=body, timeout=timeout, headers={
            'x-goog-api-key': api_key, 'content-type': 'application/json',
        })
    except requests.RequestException as exc:
        _logger.warning('Gemini API call failed: %s', exc)
        raise UserError(env._('Could not reach the Gemini API: %s', exc)) from exc
    if response.status_code >= 400:
        detail = _error_detail(response)
        _logger.warning('Gemini API returned %s: %s', response.status_code, detail)
        raise UserError(env._('Gemini API error (%(status)s): %(detail)s', status=response.status_code, detail=detail))
    payload = response.json()
    parts = (payload.get('candidates') or [{}])[0].get('content', {}).get('parts', [])
    return ''.join(part.get('text', '') for part in parts)


def ai_parse_json(text):
    """Parse a JSON answer, tolerating code fences and stray text around it; None if not JSON."""
    text = (text or '').strip()
    if text.startswith('```'):
        text = text.strip('`')
        if text.lower().startswith('json'):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    for opener, closer in (('{', '}'), ('[', ']')):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                continue
    return None


def ai_request_json(env, prompt, system='', max_tokens=4000, timeout=180):
    """ai_request_text + ai_parse_json, raising a UserError when the answer isn't a JSON object."""
    text = ai_request_text(env, prompt, system=system, max_tokens=max_tokens, timeout=timeout)
    data = ai_parse_json(text)
    if not isinstance(data, dict):
        _logger.warning('Could not parse AI response as JSON: %s', (text or '')[:2000])
        raise UserError(env._('The AI response could not be understood. Please try again.\n\n'
                          'Start of the response:\n%s', (text or '')[:500]))
    return data


class DevAi(models.AbstractModel):
    """AI status for views, the progress overlay and the other Development apps."""
    _name = 'dev.ai'
    _description = 'Development AI'

    @api.model
    def _available(self):
        return bool(ai_credentials(self.env)[1])

    @api.model
    def _provider_label(self):
        return PROVIDER_LABELS.get(ai_credentials(self.env)[0], _('the AI'))

    @api.model
    def _request_json(self, prompt, system='', max_tokens=4000):
        return ai_request_json(self.env, prompt, system=system, max_tokens=max_tokens)

    @api.model
    def _check_available(self):
        if not self._available():
            raise UserError(no_ai_message(self.env))

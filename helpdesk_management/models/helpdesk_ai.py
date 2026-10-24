"""AI helpers for the Helpdesk.

The Helpdesk has no AI credentials of its own: it uses the keys from General
Settings > Integrations (claude_ai_settings) - Claude when a Claude key is set,
otherwise Google Gemini. With no key set, no ticket is sent to an AI.
"""
import json
import logging

import requests

from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CLAUDE_API_URL = 'https://api.anthropic.com/v1/messages'
CLAUDE_MODEL = 'claude-sonnet-5-5'
CLAUDE_API_VERSION = '2023-06-01'
# Lets the API retry a declined request on a suitable model instead of failing.
CLAUDE_FALLBACK_BETA = 'server-side-fallback-2026-07-01'
GEMINI_MODEL = 'gemini-2.5-flash'
GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent'

NO_AI_MESSAGE = ('No AI is set up. Add a Claude AI or Google Gemini API key in '
                 'Settings > General Settings > Integrations.')


def ai_credentials(env):
    """(provider, api key) from General Settings, or (None, '') when no AI is set up."""
    params = env['ir.config_parameter'].sudo()
    claude_key = (params.get_param('claude_ai_settings.api_key') or '').strip()
    if claude_key:
        return 'claude', claude_key
    gemini_key = (params.get_param('claude_ai_settings.gemini_api_key') or '').strip()
    if gemini_key:
        return 'gemini', gemini_key
    return None, ''


def ai_provider_label(env):
    provider, _key = ai_credentials(env)
    return {'claude': 'Claude', 'gemini': 'Gemini'}.get(provider, 'the AI')


def ai_request_text(env, prompt, system='', max_tokens=4000, timeout=120):
    """Send one prompt to the configured AI and return its answer, raising UserError on failure."""
    provider, api_key = ai_credentials(env)
    if not api_key:
        raise UserError(NO_AI_MESSAGE)
    if provider == 'claude':
        return _claude(api_key, prompt, system, max_tokens, timeout)
    return _gemini(api_key, prompt, system, max_tokens, timeout)


def _claude(api_key, prompt, system, max_tokens, timeout):
    body = {
        'model': CLAUDE_MODEL,
        'max_tokens': max_tokens,
        'messages': [{'role': 'user', 'content': prompt}],
        'fallbacks': 'default',
    }
    if system:
        body['system'] = system
    try:
        response = requests.post(
            CLAUDE_API_URL,
            headers={
                'x-api-key': api_key,
                'anthropic-version': CLAUDE_API_VERSION,
                'anthropic-beta': CLAUDE_FALLBACK_BETA,
                'content-type': 'application/json',
            },
            json=body,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        _logger.warning('Claude API call failed: %s', exc)
        raise UserError('Could not reach the Claude API: %s' % exc) from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get('error', {}).get('message') or response.text
        except ValueError:
            detail = response.text
        _logger.warning('Claude API returned %s: %s', response.status_code, detail)
        raise UserError('Claude API error (%s): %s' % (response.status_code, detail))
    payload = response.json()
    if payload.get('stop_reason') == 'refusal':
        raise UserError('Claude declined this request. Please review the ticket and try again.')
    return ''.join(
        block.get('text', '') for block in payload.get('content', []) if block.get('type') == 'text'
    )


def _gemini(api_key, prompt, system, max_tokens, timeout):
    body = {
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'generationConfig': {'maxOutputTokens': max_tokens},
    }
    if system:
        body['systemInstruction'] = {'parts': [{'text': system}]}
    try:
        response = requests.post(
            GEMINI_API_URL % GEMINI_MODEL,
            headers={'x-goog-api-key': api_key, 'content-type': 'application/json'},
            json=body,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        _logger.warning('Gemini API call failed: %s', exc)
        raise UserError('Could not reach the Gemini API: %s' % exc) from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get('error', {}).get('message') or response.text
        except ValueError:
            detail = response.text
        _logger.warning('Gemini API returned %s: %s', response.status_code, detail)
        raise UserError('Gemini API error (%s): %s' % (response.status_code, detail))
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
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except ValueError:
            pass
    return None


def ai_request_json(env, prompt, system='', max_tokens=4000, timeout=120):
    """ai_request_text + ai_parse_json, raising a UserError when the answer isn't a JSON object."""
    text = ai_request_text(env, prompt, system=system, max_tokens=max_tokens, timeout=timeout)
    data = ai_parse_json(text)
    if not isinstance(data, dict):
        _logger.warning('Could not parse AI response as JSON: %s', (text or '')[:2000])
        raise UserError(
            'The AI response could not be understood. Please try again.\n\n'
            'Start of the response:\n%s' % (text or '')[:500]
        )
    return data

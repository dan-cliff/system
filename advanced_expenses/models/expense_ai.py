"""AI helpers for Expenses (copied from dev_management/models/dev_ai.py, see CLAUDE.md > AI keys).

Expenses has no AI credentials of its own. It uses the first key it finds,
preferring Claude/Anthropic and falling back to Google Gemini:

1. Claude AI key in Settings > General Settings > Integrations (claude_ai_settings),
2. Anthropic key of the Odoo AI app (ai / ai_anthropic),
3. Google Gemini key in Settings > General Settings > Integrations,
4. Google key of the Odoo AI app.

Neither AI app is a dependency: when none is installed, or no key is set, the
AI buttons are hidden and an explicit call raises a friendly UserError.

Unlike dev_ai, requests here carry a file (the receipt) next to the prompt.
"""
import base64
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

KEY_PARAMS = [
    ('claude', 'claude_ai_settings.api_key'),
    ('claude', 'ai.anthropic_key'),
    ('gemini', 'claude_ai_settings.gemini_api_key'),
    ('gemini', 'ai.google_key'),
]
PROVIDER_LABELS = {'claude': 'Claude', 'gemini': 'Gemini'}

# Receipt files the AI can read.
IMAGE_TYPES = ('image/jpeg', 'image/png', 'image/gif', 'image/webp')
PDF_TYPE = 'application/pdf'
MAX_FILE_BYTES = 20 * 1024 * 1024


def ai_credentials(env):
    """(provider, api key) of the first AI key set, or (None, '') when no AI is set up."""
    params = env['ir.config_parameter'].sudo()
    for provider, param in KEY_PARAMS:
        key = (params.get_param(param) or '').strip()
        if key:
            return provider, key
    return None, ''


def ai_available(env):
    return bool(ai_credentials(env)[1])


def provider_label(env):
    return PROVIDER_LABELS.get(ai_credentials(env)[0], 'AI')


def no_ai_message(env):
    return env._('No AI is set up. Add a Claude AI (preferred) or Google Gemini API key in '
                 'Settings > General Settings > Integrations, or in the Odoo AI app settings.')


def json_object(**properties):
    """A JSON schema for an object with these properties, all required (as structured outputs need)."""
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


def _error_detail(response):
    try:
        return response.json().get('error', {}).get('message') or response.text
    except ValueError:
        return response.text


def ai_read_file(env, prompt, data, mimetype, system='', schema=None, max_tokens=2000, timeout=180):
    """Send ``prompt`` with one file (raw bytes) to the configured AI and return its text answer."""
    provider, api_key = ai_credentials(env)
    if not api_key:
        raise UserError(no_ai_message(env))
    if len(data) > MAX_FILE_BYTES:
        raise UserError(env._('The receipt is too large for the AI to read (20 MB at most).'))
    encoded = base64.b64encode(data).decode()
    if provider == 'claude':
        return _claude(env, api_key, prompt, encoded, mimetype, system, schema, max_tokens, timeout)
    return _gemini(env, api_key, prompt, encoded, mimetype, system, schema, max_tokens, timeout)


def _claude(env, api_key, prompt, encoded, mimetype, system, schema, max_tokens, timeout):
    block_type = 'document' if mimetype == PDF_TYPE else 'image'
    body = {
        'model': CLAUDE_MODEL,
        'max_tokens': max_tokens,
        'messages': [{'role': 'user', 'content': [
            {'type': block_type, 'source': {'type': 'base64', 'media_type': mimetype, 'data': encoded}},
            {'type': 'text', 'text': prompt},
        ]}],
        'fallbacks': 'default',
    }
    if system:
        body['system'] = system
    if schema:
        body['output_config'] = {'format': {'type': 'json_schema', 'schema': schema}}
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
        raise UserError(env._('Claude API error (%(status)s): %(detail)s',
                              status=response.status_code, detail=detail))
    payload = response.json()
    if payload.get('stop_reason') == 'refusal':
        raise UserError(env._('Claude declined to read this receipt.'))
    if payload.get('stop_reason') == 'max_tokens':
        raise UserError(env._("The AI's answer was cut off. Please try again."))
    return ''.join(block.get('text', '') for block in payload.get('content', []) if block.get('type') == 'text')


def _gemini(env, api_key, prompt, encoded, mimetype, system, schema, max_tokens, timeout):
    body = {
        'contents': [{'role': 'user', 'parts': [
            {'inline_data': {'mime_type': mimetype, 'data': encoded}},
            {'text': prompt},
        ]}],
        'generationConfig': {'maxOutputTokens': max_tokens},
    }
    if schema:
        body['generationConfig']['responseMimeType'] = 'application/json'
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
        raise UserError(env._('Gemini API error (%(status)s): %(detail)s',
                              status=response.status_code, detail=detail))
    candidate = (response.json().get('candidates') or [{}])[0]
    if candidate.get('finishReason') == 'MAX_TOKENS':
        raise UserError(env._("The AI's answer was cut off. Please try again."))
    return ''.join(part.get('text', '') for part in candidate.get('content', {}).get('parts', []))

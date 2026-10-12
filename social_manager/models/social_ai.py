"""AI helpers for Social Manager.

Social Manager has no AI credentials of its own: it uses the keys from
General Settings > Integrations (claude_ai_settings) - Claude when a Claude
key is set, otherwise Google Gemini. The Social Manager settings only decide
whether content may be shared with the AI (AI Analysis / AI Recommendations).
"""
import json
import logging

import requests

from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CLAUDE_API_URL = 'https://api.anthropic.com/v1/messages'
CLAUDE_MODEL = 'claude-opus-5-5'
CLAUDE_API_VERSION = '2023-06-01'
# Lets the API retry a declined request on a suitable model instead of failing.
CLAUDE_FALLBACK_BETA = 'server-side-fallback-2026-07-01'
GEMINI_MODEL = 'gemini-2.5-flash'
GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent'

PARAM_AI_ANALYSIS = 'social_manager.ai_analysis'
PARAM_AI_RECOMMENDATIONS = 'social_manager.ai_recommendations'


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


def _flag(env, param):
    return env['ir.config_parameter'].sudo().get_param(param) in ('True', 'true', '1')


def ai_analysis_enabled(env):
    """AI Analysis is ticked in the Social Manager settings and an AI key is set."""
    return _flag(env, PARAM_AI_ANALYSIS) and bool(ai_credentials(env)[1])


def ai_recommendations_enabled(env):
    """AI Recommendations is ticked in the Social Manager settings and an AI key is set."""
    return _flag(env, PARAM_AI_RECOMMENDATIONS) and bool(ai_credentials(env)[1])


def ai_check(env, param, feature):
    """Raise a clear error when an AI feature can't run."""
    if not _flag(env, param):
        raise UserError(
            '%s is turned off. Turn it on in Settings > Social Manager > Integrations.' % feature
        )
    if not ai_credentials(env)[1]:
        raise UserError(
            'No AI is set up. Add a Claude AI or Google Gemini API key in '
            'Settings > General Settings > Integrations.'
        )


def ai_request_text(env, prompt, system='', max_tokens=16000, timeout=300):
    """Send one prompt to the configured AI and return its answer, raising UserError on failure."""
    provider, api_key = ai_credentials(env)
    if not api_key:
        raise UserError(
            'No AI is set up. Add a Claude AI or Google Gemini API key in '
            'Settings > General Settings > Integrations.'
        )
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
        raise UserError('Claude declined this request. Please review the content and try again.')
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
    for open_char, close_char in ('{', '}'), ('[', ']'):
        start = text.find(open_char)
        end = text.rfind(close_char)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                continue
    return None


def ai_request_json(env, prompt, system='', max_tokens=16000, timeout=300):
    """ai_request_text + ai_parse_json, raising a UserError when the answer isn't JSON."""
    text = ai_request_text(env, prompt, system=system, max_tokens=max_tokens, timeout=timeout)
    data = ai_parse_json(text)
    if data is None:
        _logger.warning('Could not parse AI response as JSON: %s', (text or '')[:2000])
        raise UserError(
            'The AI response could not be understood. Please try again.\n\n'
            'Start of the response:\n%s' % (text or '')[:500]
        )
    return data


def plural(count, word, words=None):
    """'1 post', '3 posts'."""
    return '%d %s' % (count, word if count == 1 else (words or word + 's'))


def ai_job_action(records, method, title, steps_method='get_ai_job_steps'):
    """Client action that runs `method` on `records` behind the AI progress overlay."""
    return {
        'type': 'ir.actions.client',
        'tag': 'social_manager_ai_job',
        'params': {
            'model': records._name,
            'ids': records.ids,
            'method': method,
            'steps_method': steps_method,
            'title': title,
        },
    }

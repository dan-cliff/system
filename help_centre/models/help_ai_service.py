"""
Help Centre AI Service
======================
Abstract model that provides AI text generation for article creation and the
chat bot.  Automatically discovers the configured provider by checking (in
order):
  1. ai.anthropic_key  → Anthropic Claude
  2. ai.openai_key     → OpenAI GPT-4o
  3. ai.google_key     → Google Gemini
"""

import logging
import re

import requests as _requests

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_CHATBOT_SYSTEM = """\
You are a friendly and knowledgeable Help Centre assistant for an Odoo ERP system.

Your role:
1. Answer questions about Odoo features clearly and accurately.
2. Provide numbered, step-by-step instructions when asked how to complete a task.
3. Reference the help articles provided when they are relevant.
4. Keep responses concise, actionable, and in plain language.

Formatting rules:
- Use numbered lists (1. 2. 3.) for sequential steps.
- Use "→" to show menu navigation paths, e.g. "Go to Sales → Orders → Quotations".
- Bold **key terms**, button names, and field labels.
- Never use markdown code fences — this is a chat interface.

Relevant Help Centre articles (use these where applicable):
{article_context}

If the question isn't covered by the articles above, use your general Odoo knowledge.
"""

_GENERATE_SYSTEM = """\
You are an expert Odoo consultant writing a professional Help Centre article.

Output requirements:
- Write ONLY valid HTML body content — no <html>, <head>, or <body> wrapper tags.
- Use Bootstrap-compatible tags: h2, h3, h4, p, ul, ol, li, strong, em, code, table, div.
- Structure: brief introduction → main content (numbered steps where applicable) → tips → summary.
- Tips: <div class="alert alert-info"><strong>Tip:</strong> …</div>
- Warnings: <div class="alert alert-warning"><strong>Note:</strong> …</div>
- Navigation paths: <code>Menu → Submenu → Option</code>
- Do NOT use markdown, code fences, or any text outside valid HTML tags.
- Target length: 400–800 words of readable content.
"""


class HelpAiService(models.AbstractModel):
    _name = 'help.ai.service'
    _description = 'Help Centre AI Service'

    # ── Provider discovery ─────────────────────────────────────────────────────

    def _get_provider_config(self):
        """Returns (provider, model, api_key) for the first configured provider."""
        params = self.env['ir.config_parameter'].sudo()

        anthropic_key = params.get_param('ai.anthropic_key', '')
        if anthropic_key:
            model = params.get_param('help_centre.ai_model', 'claude-sonnet-4-5')
            return 'anthropic', model, anthropic_key

        openai_key = params.get_param('ai.openai_key', '')
        if openai_key:
            return 'openai', 'gpt-4o', openai_key

        gemini_key = params.get_param('ai.google_key', '')
        if gemini_key:
            return 'gemini', 'gemini-2.5-flash', gemini_key

        return None, None, None

    def _assert_configured(self, provider):
        if not provider:
            raise UserError(
                _('No AI provider configured. '
                  'Go to Settings → AI and enter an Anthropic, OpenAI, or Gemini API key.')
            )

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate_article(self, topic, audience_label, module_names, style_hint=''):
        """Generate an HTML article body from a topic prompt."""
        provider, model, api_key = self._get_provider_config()
        self._assert_configured(provider)

        user_prompt = (
            f"Topic: {topic}\n"
            f"Audience: {audience_label}\n"
            f"Odoo modules covered: {module_names or 'General'}\n"
        )
        if style_hint:
            user_prompt += f"Style/focus: {style_hint}\n"

        return self._call(provider, model, api_key, _GENERATE_SYSTEM, user_prompt, temperature=0.7)

    def chat(self, messages, article_context=''):
        """
        Generate a chatbot reply.

        :param messages: list of {'role': 'user'|'assistant', 'content': str}
        :param article_context: pre-formatted context string from relevant articles
        """
        provider, model, api_key = self._get_provider_config()
        self._assert_configured(provider)

        system = _CHATBOT_SYSTEM.format(article_context=article_context or 'No specific articles found.')
        return self._call_with_history(provider, model, api_key, system, messages, temperature=0.5)

    # ── Dispatch ───────────────────────────────────────────────────────────────

    def _call(self, provider, model, api_key, system, user_prompt, temperature=0.7):
        messages = [{'role': 'user', 'content': user_prompt}]
        return self._call_with_history(provider, model, api_key, system, messages, temperature)

    def _call_with_history(self, provider, model, api_key, system, messages, temperature=0.5):
        try:
            if provider == 'anthropic':
                return self._anthropic(api_key, model, system, messages, temperature)
            elif provider == 'openai':
                return self._openai(api_key, model, system, messages, temperature)
            elif provider == 'gemini':
                return self._gemini(api_key, model, system, messages, temperature)
        except _requests.exceptions.Timeout:
            raise UserError(_('The AI provider timed out. Please try again.'))
        except _requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else '?'
            raise UserError(_('AI provider returned HTTP %s. Check your API key in Settings → AI.') % status)
        raise UserError(_('Unknown AI provider: %s') % provider)

    # ── Provider implementations ───────────────────────────────────────────────

    def _anthropic(self, api_key, model, system, messages, temperature):
        resp = _requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            json={
                'model': model,
                'max_tokens': 8192,
                'temperature': min(1.0, max(0.0, temperature)),
                'system': system,
                'messages': messages,
            },
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json()['content'][0]['text']

    def _openai(self, api_key, model, system, messages, temperature):
        all_messages = [{'role': 'system', 'content': system}] + messages
        resp = _requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': model,
                'temperature': temperature,
                'messages': all_messages,
                'max_tokens': 4096,
            },
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']

    def _gemini(self, api_key, model, system, messages, temperature):
        # Convert to Gemini format
        contents = []
        for msg in messages:
            role = 'user' if msg['role'] == 'user' else 'model'
            contents.append({'role': role, 'parts': [{'text': msg['content']}]})

        resp = _requests.post(
            f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}',
            headers={'Content-Type': 'application/json'},
            json={
                'system_instruction': {'parts': [{'text': system}]},
                'contents': contents,
                'generationConfig': {
                    'temperature': temperature,
                    'maxOutputTokens': 4096,
                },
            },
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json()['candidates'][0]['content']['parts'][0]['text']

    # ── Article search helper (used by chatbot) ────────────────────────────────

    def search_articles_for_context(self, query, include_internal=False, limit=4):
        """
        Full-text search on articles; returns (articles, context_string).
        Falls back to ilike when no FTS matches.
        """
        domain = [('state', '=', 'published')]
        if not include_internal:
            domain += [('audience', 'in', ('external', 'both'))]

        articles = self._fts_search(query, domain, limit)
        if not articles:
            articles = self.env['help.article'].sudo().search(
                domain + ['|',
                          ('name', 'ilike', query),
                          ('summary', 'ilike', query)],
                limit=limit,
            )

        if not articles:
            articles = self.env['help.article'].sudo().search(domain, limit=limit)

        context = self._build_context(articles)
        return articles, context

    def _fts_search(self, query, domain, limit):
        """PostgreSQL plainto_tsquery full-text search.

        In Odoo 19, translated fields (name, summary, content) are stored as
        JSONB.  We extract the 'en_US' value with ->>'en_US'; for any locale
        that hasn't been translated the key may be absent, so COALESCE handles
        that gracefully.

        The query is wrapped in a savepoint so a failure does NOT abort the
        outer transaction — without this the ilike fallback query would also
        fail with "transaction aborted".
        """
        # Build a WHERE clause from the ORM domain safely
        # We keep it simple: only add the audience/state filters via SQL
        audience_filter = ''
        for clause in domain:
            if isinstance(clause, (list, tuple)) and clause[0] == 'audience' and clause[1] == 'in':
                vals = "','".join(clause[2])
                audience_filter = f"AND audience IN ('{vals}')"
                break

        state_filter = "AND state = 'published'"
        rows = []

        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    f"""
                    SELECT id, ts_rank(
                        to_tsvector('english',
                            coalesce(name->>'en_US', '') || ' ' ||
                            coalesce(summary->>'en_US', '') || ' ' ||
                            coalesce(regexp_replace(content->>'en_US', '<[^>]+>', ' ', 'g'), '')
                        ),
                        plainto_tsquery('english', %s)
                    ) AS rank
                    FROM help_article
                    WHERE to_tsvector('english',
                            coalesce(name->>'en_US', '') || ' ' ||
                            coalesce(summary->>'en_US', '') || ' ' ||
                            coalesce(regexp_replace(content->>'en_US', '<[^>]+>', ' ', 'g'), '')
                        ) @@ plainto_tsquery('english', %s)
                    {state_filter}
                    {audience_filter}
                    ORDER BY rank DESC
                    LIMIT %s
                    """,
                    [query, query, limit],
                )
                rows = self.env.cr.fetchall()
        except Exception:
            _logger.debug('Help Centre FTS search failed for query %r', query, exc_info=True)
        if rows:
            ids = [r[0] for r in rows]
            return self.env['help.article'].sudo().browse(ids)
        return self.env['help.article'].sudo().browse([])

    def _build_context(self, articles):
        """Build a concise context string for the chatbot system prompt."""
        if not articles:
            return ''
        parts = []
        for a in articles:
            summary = a.summary or ''
            # Strip HTML tags from a snippet of the content
            raw = re.sub(r'<[^>]+>', ' ', a.content or '')
            snippet = ' '.join(raw.split()[:80])
            parts.append(
                f'### {a.name}\n'
                f'URL: /help/article/{a.slug}\n'
                f'{summary}\n'
                f'{snippet}…'
            )
        return '\n\n'.join(parts)

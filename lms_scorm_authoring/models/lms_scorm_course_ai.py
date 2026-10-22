"""Generate a course's slides with AI from the editor.

Uses the API keys on Settings › General Settings › Integrations (AI
Integration Settings): Claude first, Google Gemini if Claude isn't set up or
fails. The editor drives it in three calls so its progress overlay can show
each step: ``editor_ai_check`` (what will be asked for), ``editor_ai_write``
(the AI writes the outline) and ``editor_ai_apply`` (the outline becomes
slides).
"""
import json
import logging
import time

import requests

from odoo import _, api, models
from odoo.exceptions import UserError

from ..lib.ai_course_builder import COURSE_SCHEMA, build_slides, plan_course

_logger = logging.getLogger(__name__)

CLAUDE_URL = 'https://api.anthropic.com/v1/messages'
CLAUDE_API_VERSION = '2023-06-01'
CLAUDE_MODEL = 'claude-opus-5-5'
# Retried once: rate limits, overload and server errors.
CLAUDE_ATTEMPTS = 2
RETRY_STATUSES = (429, 500, 502, 503, 504, 529)
GEMINI_MODEL = 'gemini-2.5-flash'
GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent'

SYSTEM_PROMPT = """You are an instructional designer writing self-paced eLearning courses, in the \
style of Articulate Rise, iSpring and EasyGenerator: short slides, one idea per slide, plain \
language, practical examples. Learners work through the slides in order on a laptop or tablet.

Slide kinds:
- title: the opening slide. title is the course name; one short paragraph says what the learner \
will be able to do.
- content: a heading (title), 1-3 short paragraphs (under 60 words each) and/or 3-6 bullets \
(under 15 words each). Don't repeat the paragraphs in the bullets.
- interaction: something to explore. interaction is "tabs" (parallel topics), "accordion" \
(steps, FAQs or details) or "flip_cards" (term and meaning, myth and fact; 2-4 cards); items \
holds 2-6 entries with a short title and 1-3 sentences of text. One optional intro paragraph.
- knowledge_check: one question that checks the content just covered. Fill in question.

Questions: type "mcq" (one right answer, 3-4 options), "mrq" (two or more right answers, 4-5 \
options) or "truefalse" (exactly the options "True" and "False"). Make wrong answers plausible. \
Feedback explains why in one or two sentences.

Rules:
- Every slide has every field: use empty strings and empty lists for what doesn't apply, \
interaction "none" on non-interaction slides, and a placeholder question (type "mcq", empty \
prompt, empty options) on slides that are not knowledge checks.
- notes: one or two sentences of narration or facilitator notes for the slide.
- exam: the final exam questions, only when asked for; otherwise an empty list. Exam questions \
cover the whole course and don't repeat the knowledge checks word for word.
- End the content with a short summary slide (kind content) of the key points.
- description: one or two sentences for the course's start screen.
- No markdown, HTML or emoji in any text.
- Use Australian English."""


class LmsScormCourse(models.Model):
    _inherit = 'lms.scorm.course'

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------
    @api.model
    def _ai_providers(self):
        """[(api key, label, method)] in the order to try them: Claude first."""
        params = self.env['ir.config_parameter'].sudo()
        providers = []
        claude_key = params.get_param('claude_ai_settings.api_key')
        if claude_key:
            providers.append((claude_key, 'Claude', self._ai_claude))
        gemini_key = params.get_param('claude_ai_settings.gemini_api_key')
        if gemini_key:
            providers.append((gemini_key, 'Google Gemini', self._ai_gemini))
        return providers

    @api.model
    def _ai_claude(self, api_key, system, user_prompt):
        """Claude over its HTTP API (there is no SDK on the server), streamed: a
        whole course takes a while to write. The server-side fallback re-runs
        the request on another model if this one declines."""
        body = {
            'model': CLAUDE_MODEL,
            'max_tokens': 64000,
            'stream': True,
            'fallbacks': 'default',
            'output_config': {
                'effort': 'medium',
                'format': {'type': 'json_schema', 'schema': COURSE_SCHEMA},
            },
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
                with requests.post(CLAUDE_URL, headers=headers, json=body, stream=True,
                                   timeout=(15, 900)) as response:
                    if response.status_code in RETRY_STATUSES and attempt + 1 < CLAUDE_ATTEMPTS:
                        time.sleep(2 * (attempt + 1))
                        continue
                    if response.status_code >= 400:
                        raise UserError(self._ai_claude_error(response))
                    text, stop_reason = self._ai_read_claude_stream(response)
                break
            except requests.RequestException as error:
                if attempt + 1 < CLAUDE_ATTEMPTS:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise UserError(_('Could not reach Claude: %s', error)) from error
        if stop_reason == 'refusal':
            raise UserError(_('Claude declined to write this course.'))
        if stop_reason == 'max_tokens':
            raise UserError(_('The course was too long to finish; ask for a shorter course.'))
        return json.loads(text)

    @api.model
    def _ai_read_claude_stream(self, response):
        """The text and stop reason of a streamed (server-sent events) reply."""
        text, stop_reason = [], None
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith('data:'):
                continue
            event = json.loads(line[5:].strip())
            kind = event.get('type')
            if kind == 'content_block_delta' and event['delta'].get('type') == 'text_delta':
                text.append(event['delta']['text'])
            elif kind == 'message_delta':
                stop_reason = event['delta'].get('stop_reason') or stop_reason
            elif kind == 'error':
                raise UserError(_('Claude returned an error: %s',
                                  event.get('error', {}).get('message') or event))
        return ''.join(text), stop_reason

    @api.model
    def _ai_claude_error(self, response):
        if response.status_code == 401:
            return _('Claude rejected the API key.')
        try:
            message = response.json().get('error', {}).get('message') or response.text
        except ValueError:
            message = response.text
        return _('Claude returned an error (%(status)s): %(message)s',
                 status=response.status_code, message=message[:500])

    @api.model
    def _ai_gemini(self, api_key, system, user_prompt):
        try:
            response = requests.post(
                GEMINI_URL % GEMINI_MODEL,
                params={'key': api_key},
                json={
                    'system_instruction': {'parts': [{'text': system + '\n\nReply with only a JSON object '
                                                      'matching this JSON schema:\n' + json.dumps(COURSE_SCHEMA)}]},
                    'contents': [{'role': 'user', 'parts': [{'text': user_prompt}]}],
                    'generationConfig': {'responseMimeType': 'application/json', 'maxOutputTokens': 65536},
                },
                timeout=600,
            )
            response.raise_for_status()
            text = response.json()['candidates'][0]['content']['parts'][0]['text']
        except requests.HTTPError as error:
            raise UserError(_('Google Gemini returned an error (%s).', error.response.status_code)) from error
        except (requests.RequestException, KeyError, IndexError, ValueError) as error:
            raise UserError(_('Could not get an answer from Google Gemini: %s', error)) from error
        return json.loads(text)

    # ------------------------------------------------------------------
    # Editor calls
    # ------------------------------------------------------------------
    def _ai_check_allowed(self):
        self.ensure_one()
        if not self._editor_permissions()['can_edit']:
            raise UserError(_('This version can no longer be edited. Create a new version to make changes.'))
        if not self._ai_providers():
            raise UserError(_(
                'No AI is set up. Add a Claude AI or Google Gemini API key in Settings › '
                'General Settings › Integrations.'))

    @api.model
    def _ai_options(self, options):
        options = options or {}
        prompt = (options.get('prompt') or '').strip()
        if not prompt:
            raise UserError(_('Describe what the course should teach.'))
        try:
            minutes = int(options.get('minutes') or 15)
        except (TypeError, ValueError):
            minutes = 15
        return {
            'prompt': prompt[:6000],
            'include_checks': bool(options.get('include_checks')),
            'include_exam': bool(options.get('include_exam')),
            'minutes': minutes,
            'replace': bool(options.get('replace')),
        }

    def editor_ai_check(self, options):
        """What will be asked for, so the progress overlay can say it."""
        self._ai_check_allowed()
        opts = self._ai_options(options)
        plan = plan_course(opts['minutes'], opts['include_checks'], opts['include_exam'])
        labels = [label for _key, label, _method in self._ai_providers()]
        topic = opts['prompt'].splitlines()[0]
        return dict(plan, provider=labels[0], fallback=labels[1] if len(labels) > 1 else False,
                    topic=topic[:80] + ('…' if len(topic) > 80 else ''))

    def _ai_user_prompt(self, opts, plan):
        lines = [
            'Write an eLearning course for this brief:',
            opts['prompt'],
            'It should take about %d minutes to complete: about %d content and interaction '
            'slides (including the title and summary slides), with interactions on roughly '
            'a third of them.' % (plan['minutes'], plan['content_slides']),
        ]
        if plan['knowledge_checks']:
            lines.append('Put %d knowledge_check slides through the course, each straight after '
                         'the content it checks.' % plan['knowledge_checks'])
        else:
            lines.append('Do not include knowledge_check slides.')
        if plan['exam_questions']:
            lines.append('Write a final exam of %d questions in exam.' % plan['exam_questions'])
        else:
            lines.append('Leave exam empty.')
        if self.name and self.name.strip().lower() not in ('new course', 'untitled'):
            lines.append('The course is called "%s".' % self.name)
        return '\n\n'.join(lines)

    def editor_ai_write(self, options):
        """Have the AI write the course outline. Returns {'answer', 'provider'}."""
        self._ai_check_allowed()
        opts = self._ai_options(options)
        plan = plan_course(opts['minutes'], opts['include_checks'], opts['include_exam'])
        user_prompt = self._ai_user_prompt(opts, plan)
        errors = []
        for api_key, label, generate in self._ai_providers():
            try:
                answer = generate(api_key, SYSTEM_PROMPT, user_prompt)
                if not isinstance(answer, dict) or not answer.get('slides'):
                    raise ValueError('the answer has no slides')
                return {'answer': answer, 'provider': label}
            except (UserError, ValueError, TypeError, KeyError) as error:
                _logger.warning('SCORM AI course generator: %s failed: %s', label, error)
                errors.append('%s: %s' % (label, error))
        raise UserError(_('The course could not be generated.\n\n%s', '\n'.join(errors)))

    def editor_ai_apply(self, answer, options):
        """Turn the AI's outline into slides; returns the editor's data."""
        self._ai_check_allowed()
        opts = self._ai_options(options)
        slides, warnings = build_slides(answer, self.slide_width, self.slide_height,
                                        opts['include_checks'], opts['include_exam'],
                                        self.passing_score or 80)
        if not slides:
            raise UserError(_('The AI did not write any usable slides. Try again with more detail.'))
        Slide = self.env['lms.scorm.slide']
        if opts['replace']:
            self.slide_ids.unlink()
        sequence = max(self.slide_ids.mapped('sequence') or [0])
        vals_list = []
        for data in slides:
            sequence += 1
            vals = Slide._editor_vals(data, sequence)
            vals['course_id'] = self.id
            vals_list.append(vals)
        Slide.create(vals_list)
        course_vals = {}
        if opts['include_exam']:
            course_vals['require_pass'] = True
        if not self.description and (answer or {}).get('description'):
            course_vals['description'] = str(answer['description'])[:1000]
        if course_vals:
            self.write(course_vals)
        self.message_post(body=_('%(count)s slide(s) generated with AI from: %(prompt)s',
                                 count=len(vals_list), prompt=opts['prompt'][:300]))
        data = self.editor_load()
        data['ai_result'] = {'slides': len(vals_list), 'warnings': warnings,
                             'require_pass': bool(opts['include_exam'])}
        return data

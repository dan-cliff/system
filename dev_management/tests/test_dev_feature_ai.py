from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.dev_management.models import dev_ai

AI = 'odoo.addons.dev_management.models.dev_ai'


class FakeResponse:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data


@tagged('post_install', '-at_install')
class TestFeatureAi(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        params = cls.env['ir.config_parameter'].sudo()
        params.set_param('claude_ai_settings.api_key', 'sk-test')
        params.set_param('claude_ai_settings.gemini_api_key', '')
        cls.feature = cls.env['dev.feature'].create({
            'name': 'Offline mode',
            'summary': 'Let field staff work without a connection.',
            'description': '<p>Staff lose signal on farms.</p>',
            'criterion_ids': [(0, 0, {'name': 'Met criterion', 'done': True}),
                              (0, 0, {'name': 'Old open criterion'})],
        })

    def test_draft_then_rerun_with_context(self):
        feature = self.feature
        self.assertFalse(feature.ai_spec_drafted)
        draft = {'description': '<p>Draft</p>', 'specification': '<p>Spec</p>', 'acceptance_criteria': ['New A']}
        with patch(AI + '.ai_request_json', return_value=draft) as request:
            feature.action_ai_run('feature_spec')
        self.assertTrue(feature.ai_spec_drafted, 'The Draft button turns into Rerun')
        self.assertEqual(feature.criterion_ids.mapped('name'), ['Met criterion', 'Old open criterion', 'New A'])
        self.assertNotIn('Additional context', request.call_args.args[1])

        rework = {'description': '<p>Reworked</p>', 'specification': '<p>Spec 2</p>',
                  'acceptance_criteria': ['Met criterion', 'Works offline for 7 days']}
        info = feature.get_ai_job_info('feature_spec', prompt='Must work for a week offline')
        self.assertIn('additional context', info['step'])
        with patch(AI + '.ai_request_json', return_value=rework) as request:
            feature.action_ai_run('feature_spec', prompt='Must work for a week offline')
        sent = request.call_args.args[1]
        self.assertIn('Must work for a week offline', sent)
        self.assertIn('Met criterion (met)', sent, 'The AI gets the whole record, criteria status included')
        self.assertEqual(feature.description, '<p>Reworked</p>')
        # Met criteria are kept as they are; the others are replaced by the reworked list.
        self.assertEqual(feature.criterion_ids.mapped('name'), ['Met criterion', 'Works offline for 7 days'])
        self.assertTrue(feature.criterion_ids[0].done)

    def test_selection_edit_text_and_lines(self):
        feature = self.feature
        summary = feature.summary
        start = summary.index('field staff')
        kwargs = dict(field='summary', prompt='Be specific', selected_text='field staff',
                      old_value=summary, start=start, end=start + len('field staff'))
        with patch(AI + '.ai_request_json', return_value={'replacement': 'farm technicians'}) as request:
            feature.action_ai_run('selection_edit', **kwargs)
        self.assertEqual(feature.summary, 'Let farm technicians work without a connection.')
        self.assertIn('Be specific', request.call_args.args[1])
        # The text changed meanwhile: nothing is overwritten.
        with patch(AI + '.ai_request_json', return_value={'replacement': 'x'}), self.assertRaises(UserError):
            feature.action_ai_run('selection_edit', **kwargs)

        line = feature.criterion_ids.filtered(lambda c: c.name == 'Old open criterion')
        with patch(AI + '.ai_request_json', return_value={'replacement': 'Given a lost signal'}):
            feature.action_ai_run('selection_edit', field='criterion_ids', subfield='name', prompt='Gherkin',
                                  selected_text='Old open criterion', old_value='Old open criterion', start=0, end=18)
        self.assertEqual(line.name, 'Given a lost signal')
        # Only the enabled fields can be edited this way.
        with self.assertRaises(UserError):
            feature.action_ai_run('selection_edit', field='name', prompt='x', selected_text='Offline')

    def test_selection_edit_html(self):
        with patch(AI + '.ai_request_json', return_value={'replacement': '<p>poor <strong>4G</strong> <script>x</script></p>'}):
            result = self.feature.action_ai_run('selection_edit', field='description', prompt='Mention 4G',
                                                selected_text='lose signal', is_html=True)
        self.assertEqual(result['html'].strip(), 'poor <strong>4G</strong>', 'Inline, unwrapped and sanitised')
        self.assertEqual(self.feature.description, '<p>Staff lose signal on farms.</p>', 'The form applies it')

    def test_research(self):
        feature = self.feature
        feature.link_ids = [(0, 0, {'name': 'Known', 'url': 'https://known.example/doc'})]
        answer = ('I searched for offline sync patterns.\n\n{"findings_html": "<ul><li>Use a local queue</li></ul>", '
                  '"suggestions_html": "<ul><li>Interview 3 technicians</li></ul>", "sources": ['
                  '{"title": "Sync guide", "url": "https://docs.example/sync", "why": "Conflict handling"}, '
                  '{"title": "Made up", "url": "https://invented.example/x"}, '
                  '{"title": "Known", "url": "https://known.example/doc"}]}')
        result = {'text': answer, 'searched': True,
                  'found': {'https://docs.example/sync': 'Sync guide', 'https://known.example/doc': 'Known',
                            'https://cited.example/a': 'Cited page'},
                  'cited': ['https://docs.example/sync', 'https://cited.example/a']}
        with patch(AI + '.ai_research', return_value=result):
            message = feature.action_ai_run('feature_research')
        self.assertIn('Use a local queue', feature.research)
        self.assertIn('Interview 3 technicians', feature.research)
        self.assertIn('Staff lose signal', feature.description)
        urls = feature.link_ids.mapped('url')
        self.assertIn('https://docs.example/sync', urls)
        self.assertIn('https://cited.example/a', urls, 'Pages the answer cited are added too')
        self.assertNotIn('https://invented.example/x', urls, 'Sources not found by the searches are left out')
        self.assertEqual(urls.count('https://known.example/doc'), 1, 'No duplicates')
        self.assertIn('Conflict handling', feature.link_ids.filtered(lambda l: 'docs.example' in l.url).notes)
        self.assertIn('2 new source', message)
        # Running it again adds a new section rather than replacing the research.
        with patch(AI + '.ai_research', return_value=dict(result, searched=False, found={}, cited=[])):
            feature.action_ai_run('feature_research')
        self.assertEqual(feature.research.count('AI research ('), 2)
        self.assertIn('Web search was not available', feature.research)

    def test_claude_research_web_search(self):
        """Claude's web search: pages found, citations, and a paused turn resumed."""
        first = {'stop_reason': 'pause_turn', 'content': [
            {'type': 'server_tool_use', 'id': 's1', 'name': 'web_search', 'input': {'query': 'offline sync'}},
            {'type': 'web_search_tool_result', 'tool_use_id': 's1', 'content': [
                {'type': 'web_search_result', 'url': 'https://a.example', 'title': 'A'},
                {'type': 'web_search_result', 'url': 'https://b.example', 'title': 'B'}]}]}
        second = {'stop_reason': 'end_turn', 'content': [
            {'type': 'text', 'text': 'Local queues work ', 'citations': [
                {'type': 'web_search_result_location', 'url': 'https://a.example', 'title': 'A', 'cited_text': 'q'}]},
            {'type': 'text', 'text': '{"findings_html": "<p>x</p>"}'}]}
        calls = []

        def post(url, json=None, timeout=None, headers=None):
            calls.append(json)
            return FakeResponse(200, first if len(calls) == 1 else second)

        with patch(AI + '.requests.post', post):
            result = dev_ai.ai_research(self.env, 'Research it')
        self.assertEqual(calls[0]['tools'][0]['type'], 'web_search_20260209')
        self.assertEqual(calls[1]['messages'][-1], {'role': 'assistant', 'content': first['content']})
        self.assertEqual(result['found'], {'https://a.example': 'A', 'https://b.example': 'B'})
        self.assertEqual(result['cited'], ['https://a.example'])
        self.assertTrue(result['searched'])
        self.assertIn('{"findings_html"', result['text'])

        # Web search refused (400): answered without it, flagged as not searched.
        replies = [FakeResponse(400, {'error': {'message': 'web search is disabled'}}),
                   FakeResponse(200, {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'plain'}]})]
        with patch(AI + '.requests.post', lambda *a, **k: replies.pop(0)):
            result = dev_ai.ai_research(self.env, 'Research it')
        self.assertEqual(result, {'text': 'plain', 'found': {}, 'cited': [], 'searched': False})

    def test_gemini_research_grounding(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('claude_ai_settings.api_key', '')
        params.set_param('claude_ai_settings.gemini_api_key', 'g-key')
        payload = {'candidates': [{'content': {'parts': [{'text': 'answer'}]}, 'groundingMetadata': {
            'groundingChunks': [{'web': {'uri': 'https://g.example', 'title': 'g.example'}}]}}]}
        with patch(AI + '.requests.post', return_value=FakeResponse(200, payload)) as post:
            result = dev_ai.ai_research(self.env, 'Research it')
        self.assertEqual(post.call_args.kwargs['json']['tools'], [{'google_search': {}}])
        self.assertEqual(result['found'], {'https://g.example': 'g.example'})
        self.assertTrue(result['searched'])

    def test_json_answers_schema_truncation_and_fences(self):
        """Structured answers: schema sent, a cut-off answer retried with more room, code fences tolerated."""
        cut_off = {'stop_reason': 'max_tokens', 'content': [{'type': 'text', 'text': '{"description": "<p>Long'}]}
        complete = {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text':
                    '```json\n{"description": "<p>D</p>", "specification": "<p>S</p>", "acceptance_criteria": ["C"]}\n```'}]}
        bodies = []

        def post(url, json=None, timeout=None, headers=None):
            bodies.append(json)
            return FakeResponse(200, cut_off if len(bodies) == 1 else complete)

        with patch(AI + '.requests.post', post):
            self.feature.action_ai_run('feature_spec')
        self.assertEqual(len(bodies), 2, 'The cut-off answer is asked for again')
        self.assertEqual(bodies[0]['output_config']['format']['type'], 'json_schema')
        self.assertEqual(bodies[0]['output_config']['format']['schema']['required'],
                         ['description', 'specification', 'acceptance_criteria'])
        self.assertEqual(bodies[1]['max_tokens'], 2 * bodies[0]['max_tokens'])
        self.assertEqual(self.feature.description, '<p>D</p>')

        # Still cut off at the largest size: a clear message, not "could not be understood".
        with patch(AI + '.requests.post', return_value=FakeResponse(200, cut_off)), \
                self.assertRaisesRegex(UserError, 'too long'):
            dev_ai.ai_request_json(self.env, 'x', max_tokens=dev_ai.MAX_RETRY_TOKENS, schema={'type': 'object'})

    def test_gemini_json_mode_and_truncation(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('claude_ai_settings.api_key', '')
        params.set_param('claude_ai_settings.gemini_api_key', 'g-key')
        cut = {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': '{"a": '}]}}]}
        done = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"a": 1}'}]}}]}
        replies = [FakeResponse(200, cut), FakeResponse(200, done)]
        with patch(AI + '.requests.post', side_effect=lambda *a, **k: replies.pop(0)) as post:
            data = dev_ai.ai_request_json(self.env, 'x', schema=dev_ai.json_object(a={'type': 'integer'}))
        self.assertEqual(data, {'a': 1})
        self.assertEqual(post.call_args.kwargs['json']['generationConfig']['responseMimeType'], 'application/json')

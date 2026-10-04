import json
from unittest.mock import MagicMock, patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.custom_dashboard.models import dashboard_ai

AI = 'odoo.addons.custom_dashboard.models.dashboard_ai.CustomDashboard'


@tagged('post_install', '-at_install')
class TestDashboardAI(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(
            cls.env, login='cd_ai_manager', groups='base.group_user,custom_dashboard.group_dashboard_manager',
        )
        cls.viewer = new_test_user(
            cls.env, login='cd_ai_viewer', groups='base.group_user,custom_dashboard.group_dashboard_user',
        )
        cls.params = cls.env['ir.config_parameter'].sudo()
        cls.params.set_param(dashboard_ai.CLAUDE_KEY_PARAM, False)
        cls.params.set_param(dashboard_ai.GEMINI_KEY_PARAM, False)
        cls.Dashboard = cls.env['custom.dashboard'].with_user(cls.manager)

    def _design(self, widgets, name='Contacts Overview'):
        return {'name': name, 'description': 'Contacts at a glance', 'widgets': widgets}

    def _generate(self, design, provider='claude'):
        self.params.set_param(dashboard_ai.CLAUDE_KEY_PARAM, 'sk-test')
        answers = [{'models': ['res.partner', 'not.a.model']}, design]
        calls = []

        # A plain function, not a MagicMock: the ORM scans model methods for
        # attributes such as _ondelete, which a mock would claim to have.
        def fake_ask(model, provider, key, prompt, schema, effort='medium', timeout=None):
            calls.append(prompt)
            return answers[len(calls) - 1]

        with patch(AI + '._ai_ask', fake_ask):
            result = self.Dashboard.ai_generate('Show me my contacts', provider)
        return result, calls

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------
    def test_providers_follow_api_keys_in_order(self):
        self.assertEqual(self.Dashboard.ai_get_providers(), [])
        self.params.set_param(dashboard_ai.GEMINI_KEY_PARAM, 'gem-key')
        self.assertEqual([p['code'] for p in self.Dashboard.ai_get_providers()], ['gemini'])
        self.params.set_param(dashboard_ai.CLAUDE_KEY_PARAM, 'sk-key')
        self.assertEqual([p['code'] for p in self.Dashboard.ai_get_providers()], ['claude', 'gemini'])

    def test_viewers_get_no_ai(self):
        self.params.set_param(dashboard_ai.CLAUDE_KEY_PARAM, 'sk-key')
        Dashboard = self.env['custom.dashboard'].with_user(self.viewer)
        self.assertEqual(Dashboard.ai_get_providers(), [])
        with self.assertRaises(AccessError):
            Dashboard.ai_generate('Anything', 'claude')

    def test_missing_key_is_an_error(self):
        with self.assertRaises(UserError):
            self.Dashboard.ai_generate('Anything', 'gemini')

    # ------------------------------------------------------------------
    # Prompt
    # ------------------------------------------------------------------
    def test_design_prompt_has_library_layout_and_fields(self):
        prompt = self.Dashboard._ai_design_prompt('Contacts by country', ['res.partner'])
        self.assertIn('gridstack.js', prompt)
        self.assertIn('12 columns', prompt)
        for code in ('column', 'pivot', 'kpi', 'map', 'gauge', 'text'):
            self.assertIn('| %s |' % code, prompt)
        self.assertNotIn('| image |', prompt)
        self.assertIn('country_id (many2one -> res.country', prompt)
        self.assertIn('extended_team', prompt)

    def test_catalogue_skips_technical_models(self):
        catalogue = self.Dashboard._ai_model_catalogue()
        self.assertIn('res.partner', catalogue)
        self.assertNotIn('ir.model', catalogue)
        self.assertNotIn('custom.dashboard', catalogue)

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------
    def test_generate_builds_dashboard(self):
        result, calls = self._generate(self._design([
            {'type': 'kpi', 'title': 'Contacts', 'x': 0, 'y': 0, 'w': 3, 'h': 2, 'model': 'res.partner',
             'domain': "[('active', '=', True)]", 'target': 100, 'show_shadow': True},
            {'type': 'column', 'title': 'By Country', 'x': 0, 'y': 2, 'w': 6, 'h': 4, 'model': 'res.partner',
             'group_by': 'country_id', 'series': 'is_company', 'pivot_row_sort': 'value_desc', 'limit': 10,
             'colors': ['#112233', 'red', '#AABBCC']},
            {'type': 'pivot', 'title': 'Matrix', 'x': 6, 'y': 2, 'w': 6, 'h': 4, 'model': 'res.partner',
             'group_by': 'country_id', 'series': 'is_company', 'pivot_row_label': 'Country',
             'pivot_hide_row_totals': True},
            {'type': 'text', 'title': 'Intro', 'x': 0, 'y': 6, 'w': 12, 'h': 1, 'text_content': '<p>Hello</p>'},
        ]))
        self.assertEqual(len(calls), 2)
        # The second step only describes the models that exist.
        self.assertIn('### res.partner', calls[1])
        self.assertNotIn('not.a.model', calls[1])
        dashboard = self.env['custom.dashboard'].browse(result['dashboard_id'])
        self.assertEqual(dashboard.name, 'Contacts Overview')
        self.assertEqual(result['provider'], 'Claude AI')
        widgets = {w.name: w for w in dashboard.widget_ids}
        self.assertEqual(set(widgets), {'Contacts', 'By Country', 'Matrix', 'Intro'})
        kpi, column, pivot = widgets['Contacts'], widgets['By Country'], widgets['Matrix']
        self.assertEqual(kpi.type_code, 'kpi')
        self.assertEqual(kpi.target_value, 100)
        self.assertTrue(kpi.show_shadow)
        self.assertEqual(column.groupby_field_id.name, 'country_id')
        self.assertEqual(column.series_field_id.name, 'is_company')
        self.assertEqual((column.pivot_row_sort, column.limit), ('value_desc', 10))
        self.assertTrue(column.custom_colors)
        self.assertEqual((column.color, column.color_2), ('#112233', '#aabbcc'))
        self.assertEqual(pivot.pivot_row_label, 'Country')
        self.assertTrue(pivot.pivot_hide_row_totals)
        self.assertEqual((column.pos_x, column.pos_y, column.width, column.height), (0, 2, 6, 4))
        self.assertIn('Hello', widgets['Intro'].text_content)
        self.assertFalse(result['warnings'])

    def test_generate_repairs_bad_answers(self):
        result, _ask = self._generate(self._design([
            # Unknown type and unknown model are skipped.
            {'type': 'hologram', 'title': 'Nope', 'x': 0, 'y': 0, 'w': 3, 'h': 2},
            {'type': 'kpi', 'title': 'Elsewhere', 'x': 0, 'y': 0, 'w': 3, 'h': 2, 'model': 'not.a.model'},
            # A missing group-by field skips the chart.
            {'type': 'bar', 'title': 'No Group', 'x': 0, 'y': 0, 'w': 6, 'h': 4, 'model': 'res.partner',
             'group_by': 'no_such_field'},
            # A bad measure is dropped, the chart is kept.
            {'type': 'line', 'title': 'Trend', 'x': 0, 'y': 0, 'w': 20, 'h': 4, 'model': 'res.partner',
             'group_by': 'create_date', 'group_by_interval': 'month', 'measure': 'name'},
            # Overlaps the line chart, so it moves below it; its broken filter is removed.
            {'type': 'kpi', 'title': 'Count', 'x': 3, 'y': 1, 'w': 3, 'h': 2, 'model': 'res.partner',
             'domain': "[('no_such_field', '=', 1)]"},
        ]))
        dashboard = self.env['custom.dashboard'].browse(result['dashboard_id'])
        widgets = {w.name: w for w in dashboard.widget_ids}
        self.assertEqual(set(widgets), {'Trend', 'Count'})
        trend, count = widgets['Trend'], widgets['Count']
        self.assertEqual((trend.pos_x, trend.width), (0, 12))
        self.assertFalse(trend.measure_field_id)
        self.assertEqual(trend.groupby_interval, 'month')
        self.assertEqual(count.pos_y, 4)
        self.assertEqual(count.domain, '[]')
        self.assertEqual(len(result['warnings']), 5)

    def test_generate_with_nothing_usable_fails(self):
        with self.assertRaises(UserError):
            self._generate(self._design([
                {'type': 'kpi', 'title': 'Elsewhere', 'x': 0, 'y': 0, 'w': 3, 'h': 2, 'model': 'not.a.model'},
            ]))
        self.assertFalse(self.env['custom.dashboard'].search([('name', '=', 'Contacts Overview')]))

    # ------------------------------------------------------------------
    # Engines
    # ------------------------------------------------------------------
    def test_parse_json_handles_fences(self):
        parse = self.Dashboard._ai_parse_json
        self.assertEqual(parse('```json\n{"a": 1}\n```'), {'a': 1})
        self.assertEqual(parse('Here you go: {"a": 2} enjoy'), {'a': 2})
        with self.assertRaises(UserError):
            parse('no json here')

    def test_gemini_request(self):
        self.params.set_param(dashboard_ai.GEMINI_MODEL_PARAM, False)
        response = MagicMock(status_code=200)
        response.json.return_value = {
            'candidates': [{'content': {'parts': [{'text': json.dumps({'models': ['res.partner']})}]}}],
        }
        with patch.object(dashboard_ai.requests, 'post', return_value=response) as post:
            answer = self.Dashboard._ai_ask('gemini', 'gem-key', 'prompt', {'type': 'object'})
        self.assertEqual(answer, {'models': ['res.partner']})
        url = post.call_args.args[0]
        self.assertIn(dashboard_ai.GEMINI_MODELS[0], url)
        self.assertEqual(post.call_args.kwargs['headers'], {'x-goog-api-key': 'gem-key'})
        config = post.call_args.kwargs['json']['generationConfig']
        self.assertEqual(config['responseMimeType'], 'application/json')

    def test_gemini_falls_back_to_next_model(self):
        missing = MagicMock(status_code=404)
        ok = MagicMock(status_code=200)
        ok.json.return_value = {'candidates': [{'content': {'parts': [{'text': '{"ok": true}'}]}}]}
        with patch.object(dashboard_ai.requests, 'post', side_effect=[missing, ok]) as post:
            answer = self.Dashboard._ai_ask('gemini', 'gem-key', 'prompt', {'type': 'object'})
        self.assertEqual(answer, {'ok': True})
        self.assertIn(dashboard_ai.GEMINI_MODELS[1], post.call_args.args[0])

    def test_gemini_bad_key(self):
        with patch.object(dashboard_ai.requests, 'post', return_value=MagicMock(status_code=403)):
            with self.assertRaises(UserError):
                self.Dashboard._ai_ask('gemini', 'bad', 'prompt', {'type': 'object'})

    def _claude_response(self, status=200, body=None):
        response = MagicMock(status_code=status, headers={})
        response.json.return_value = body or {}
        response.text = json.dumps(body or {})
        return response

    def test_claude_request(self):
        body = {'stop_reason': 'end_turn', 'content': [
            {'type': 'thinking', 'thinking': ''},
            {'type': 'text', 'text': '{"models": ["res.partner"]}'},
        ]}
        with patch.object(dashboard_ai.requests, 'post', return_value=self._claude_response(body=body)) as post:
            answer = self.Dashboard._ai_ask('claude', 'sk-key', 'prompt', {'type': 'object'}, effort='low')
        self.assertEqual(answer, {'models': ['res.partner']})
        self.assertEqual(post.call_args.args[0], dashboard_ai.CLAUDE_URL)
        headers = post.call_args.kwargs['headers']
        self.assertEqual(headers['x-api-key'], 'sk-key')
        self.assertEqual(headers['anthropic-version'], '2023-06-01')
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['model'], dashboard_ai.CLAUDE_MODEL)
        self.assertEqual(payload['output_config']['effort'], 'low')
        self.assertEqual(payload['output_config']['format']['type'], 'json_schema')
        self.assertIn(self.Dashboard._ai_language(), payload['system'])

    def test_claude_errors(self):
        cases = [
            self._claude_response(401, {'error': {'message': 'invalid x-api-key'}}),
            self._claude_response(429),
            self._claude_response(400, {'error': {'message': 'bad request'}}),
            self._claude_response(body={'stop_reason': 'refusal', 'content': []}),
            self._claude_response(body={'stop_reason': 'max_tokens', 'content': []}),
        ]
        for response in cases:
            with patch.object(dashboard_ai.requests, 'post', return_value=response):
                with self.assertRaises(UserError):
                    self.Dashboard._ai_ask('claude', 'sk-key', 'prompt', {'type': 'object'})

    def test_language_follows_main_company(self):
        company = self.manager.company_id
        company.partner_id.lang = 'en_US'
        company.country_id = self.env.ref('base.au')
        language = self.Dashboard._ai_language()
        self.assertIn('English', language)
        self.assertIn('Australia', language)
        self.assertIn(language, self.Dashboard._ai_system_prompt())
        self.assertIn(language, self.Dashboard._ai_design_prompt('Contacts', ['res.partner']))

    def test_claude_retries_without_fallbacks(self):
        rejected = self._claude_response(400, {'error': {'message': 'fallbacks: not supported'}})
        ok = self._claude_response(body={'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': '{}'}]})
        with patch.object(dashboard_ai.requests, 'post', side_effect=[rejected, ok]) as post:
            self.assertEqual(self.Dashboard._ai_ask('claude', 'sk-key', 'prompt', {'type': 'object'}), {})
        self.assertNotIn('fallbacks', post.call_args.kwargs['json'])
        self.assertNotIn('anthropic-beta', post.call_args.kwargs['headers'])

    def test_claude_skips_schemas_over_its_limit(self):
        ok = self._claude_response(body={'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': '{}'}]})
        Dashboard = self.Dashboard
        self.assertGreater(Dashboard._ai_optional_count(Dashboard._ai_design_schema()), 24)
        self.assertEqual(Dashboard._ai_optional_count(Dashboard._ai_models_schema()), 0)
        with patch.object(dashboard_ai.requests, 'post', return_value=ok) as post:
            Dashboard._ai_ask('claude', 'sk-key', 'prompt', Dashboard._ai_design_schema())
        self.assertNotIn('format', post.call_args.kwargs['json']['output_config'])
        with patch.object(dashboard_ai.requests, 'post', return_value=ok) as post:
            Dashboard._ai_ask('claude', 'sk-key', 'prompt', Dashboard._ai_models_schema())
        self.assertIn('format', post.call_args.kwargs['json']['output_config'])

    def test_claude_retries_without_rejected_schema(self):
        rejected = self._claude_response(400, {'error': {'message': 'Schemas contains too many optional parameters'}})
        ok = self._claude_response(body={'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': '{"a": 1}'}]})
        with patch.object(dashboard_ai.requests, 'post', side_effect=[rejected, ok]) as post:
            answer = self.Dashboard._ai_ask('claude', 'sk-key', 'prompt', self.Dashboard._ai_models_schema())
        self.assertEqual(answer, {'a': 1})
        self.assertNotIn('format', post.call_args.kwargs['json']['output_config'])

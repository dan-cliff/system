"""Tests for wf.automation hook mechanism, trigger logic, and execution logging."""
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged('workflow_automation', 'workflow_engine')
class TestWorkflowEngine(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env['ir.model'].search(
            [('model', '=', 'res.partner')], limit=1
        )
        # Use an existing partner to avoid cross-module NOT NULL constraints
        cls.partner = cls.env['res.partner'].search(
            [('active', '=', True), ('name', '!=', False)], limit=1
        )

    def setUp(self):
        super().setUp()
        self.wf = self.env['wf.automation'].create({
            'name': 'Test Workflow',
            'model_id': self.partner_model.id,
            'trigger': 'on_create',
            'log_level': 'all',
        })

    # ------------------------------------------------------------------ #
    # Basic CRUD                                                           #
    # ------------------------------------------------------------------ #

    def test_create_workflow(self):
        """A newly created workflow has the expected field defaults."""
        self.assertEqual(self.wf.model_name, 'res.partner')
        self.assertEqual(self.wf.trigger, 'on_create')
        self.assertTrue(self.wf.active)
        self.assertEqual(self.wf.log_level, 'all')

    def test_workflow_with_steps(self):
        """Steps can be added to a workflow and are ordered by sequence."""
        step1 = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Step A',
            'step_type': 'stop_workflow',
            'sequence': 20,
        })
        step2 = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Step B',
            'step_type': 'stop_workflow',
            'sequence': 10,
        })
        ordered = self.wf.step_ids.sorted('sequence')
        self.assertEqual(ordered[0].id, step2.id)
        self.assertEqual(ordered[1].id, step1.id)

    def test_copy_workflow(self):
        """Copying a workflow copies its steps."""
        self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Original Step',
            'step_type': 'stop_workflow',
        })
        copy = self.wf.copy()
        self.assertEqual(len(copy.step_ids), 1)
        self.assertNotEqual(copy.id, self.wf.id)

    # ------------------------------------------------------------------ #
    # _get_actions                                                         #
    # ------------------------------------------------------------------ #

    def test_get_actions_matches_model_and_trigger(self):
        """_get_actions returns workflows matching model + trigger."""
        result = self.env['wf.automation']._get_actions(
            self.env['res.partner'], ['on_create']
        )
        self.assertIn(self.wf.id, result.ids)

    def test_get_actions_no_match_wrong_trigger(self):
        """_get_actions returns nothing for a non-matching trigger."""
        result = self.env['wf.automation']._get_actions(
            self.env['res.partner'], ['on_unlink']
        )
        self.assertNotIn(self.wf.id, result.ids)

    def test_get_actions_no_match_inactive(self):
        """Inactive workflows are excluded from _get_actions."""
        self.wf.active = False
        result = self.env['wf.automation']._get_actions(
            self.env['res.partner'], ['on_create']
        )
        self.assertNotIn(self.wf.id, result.ids)

    # ------------------------------------------------------------------ #
    # _filter_post                                                         #
    # ------------------------------------------------------------------ #

    def test_filter_post_empty_domain(self):
        """_filter_post with empty domain returns all records unchanged."""
        self.wf.filter_domain = '[]'
        result = self.wf._filter_post(self.partner)
        self.assertIn(self.partner.id, result.ids)

    def test_filter_post_matching_domain(self):
        """_filter_post keeps records matching the domain."""
        self.wf.filter_domain = f"[('id', '=', {self.partner.id})]"
        other = self.env['res.partner'].search(
            [('id', '!=', self.partner.id)], limit=1
        )
        result = self.wf._filter_post(self.partner | other)
        self.assertIn(self.partner.id, result.ids)
        self.assertNotIn(other.id, result.ids)

    def test_filter_post_no_match(self):
        """_filter_post returns empty recordset when no record matches."""
        self.wf.filter_domain = "[('id', '=', -1)]"
        result = self.wf._filter_post(self.partner)
        self.assertFalse(result)

    # ------------------------------------------------------------------ #
    # _check_trigger_fields                                                #
    # ------------------------------------------------------------------ #

    def test_check_trigger_fields_no_watchlist(self):
        """With no trigger_field_ids, any change should match."""
        result = self.wf._check_trigger_fields(self.partner)
        self.assertTrue(result)

    def test_check_trigger_fields_with_changed_field(self):
        """Returns True when a watched field has changed."""
        name_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.partner_model.id), ('name', '=', 'name')
        ], limit=1)
        self.wf.trigger_field_ids = [name_field.id]
        old_values = {self.partner.id: {'name': 'OldName'}}
        result = self.wf.with_context(old_values=old_values)._check_trigger_fields(self.partner)
        self.assertTrue(result)

    def test_check_trigger_fields_no_change(self):
        """Returns False when the watched field value is unchanged."""
        name_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.partner_model.id), ('name', '=', 'name')
        ], limit=1)
        self.wf.trigger_field_ids = [name_field.id]
        old_values = {self.partner.id: {'name': self.partner.name}}
        result = self.wf.with_context(old_values=old_values)._check_trigger_fields(self.partner)
        self.assertFalse(result)

    # ------------------------------------------------------------------ #
    # Execution logging                                                    #
    # ------------------------------------------------------------------ #

    def test_execution_log_created_on_process(self):
        """Running _process creates a wf.execution.log entry."""
        self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Stop',
            'step_type': 'stop_workflow',
            'sequence': 10,
        })
        self.wf._process(self.partner, 'on_create')
        logs = self.env['wf.execution.log'].search([('workflow_id', '=', self.wf.id)])
        self.assertTrue(logs, "Expected at least one execution log")

    def test_execution_log_state_success(self):
        """A workflow with no steps finishes with state='success'."""
        self.wf._process(self.partner, 'on_create')
        log = self.env['wf.execution.log'].search(
            [('workflow_id', '=', self.wf.id)], limit=1, order='id desc'
        )
        self.assertTrue(log)
        self.assertEqual(log.state, 'success')

    def test_execution_log_duration_recorded(self):
        """Execution log records a non-negative duration_ms."""
        self.wf._process(self.partner, 'on_create')
        log = self.env['wf.execution.log'].search(
            [('workflow_id', '=', self.wf.id)], limit=1, order='id desc'
        )
        self.assertGreaterEqual(log.duration_ms, 0)

    def test_log_level_none_skips_logging(self):
        """log_level='none' produces no execution log records."""
        self.wf.log_level = 'none'
        before = self.env['wf.execution.log'].search_count([('workflow_id', '=', self.wf.id)])
        self.wf._process(self.partner, 'on_create')
        after = self.env['wf.execution.log'].search_count([('workflow_id', '=', self.wf.id)])
        self.assertEqual(before, after)

    def test_log_level_error_only_no_log_on_success(self):
        """log_level='error_only' deletes the log when execution succeeds."""
        self.wf.log_level = 'error_only'
        self.wf._process(self.partner, 'on_create')
        logs = self.env['wf.execution.log'].search([('workflow_id', '=', self.wf.id)])
        self.assertFalse(logs, "Success log should be deleted with error_only level")

    def test_anti_recursion_guard(self):
        """A trigger_workflow step pointing to itself does not recurse infinitely."""
        # Add a step that triggers this same workflow on the same record.
        # The anti-recursion guard (context key __wf_action_done) should prevent
        # the sub-invocation from running again, so we end up with exactly 1 log.
        self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Self-trigger',
            'step_type': 'trigger_workflow',
            'sub_workflow_id': self.wf.id,
            'sub_workflow_record_type': 'trigger',
            'sequence': 10,
        })
        self.wf._process(self.partner, 'on_create')
        logs = self.env['wf.execution.log'].search([('workflow_id', '=', self.wf.id)])
        self.assertEqual(len(logs), 1, "Anti-recursion guard should block the recursive run")

    def test_last_run_updated_after_execution(self):
        """last_run timestamp is updated after workflow execution."""
        before = self.wf.last_run
        self.wf._process(self.partner, 'on_create')
        self.assertTrue(self.wf.last_run)
        if before:
            self.assertGreater(self.wf.last_run, before)

    # ------------------------------------------------------------------ #
    # Scheduled trigger                                                    #
    # ------------------------------------------------------------------ #

    def test_cron_scheduled_trigger(self):
        """_cron_run_scheduled_workflows runs scheduled workflows."""
        scheduled_wf = self.env['wf.automation'].create({
            'name': 'Scheduled WF',
            'model_id': self.partner_model.id,
            'trigger': 'scheduled',
            'cron_model_domain': f"[('id', '=', {self.partner.id})]",
            'log_level': 'all',
        })
        self.env['wf.automation']._cron_run_scheduled_workflows()
        logs = self.env['wf.execution.log'].search([('workflow_id', '=', scheduled_wf.id)])
        self.assertTrue(logs, "Scheduled workflow should have produced an execution log")

    def test_cron_skips_non_scheduled_workflows(self):
        """_cron_run_scheduled_workflows ignores on_create workflows."""
        self.env['wf.automation']._cron_run_scheduled_workflows()
        logs = self.env['wf.execution.log'].search([('workflow_id', '=', self.wf.id)])
        self.assertFalse(logs, "on_create workflow should not run via cron")

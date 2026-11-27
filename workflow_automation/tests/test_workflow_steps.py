"""Tests for individual wf.step execution types."""
import datetime
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo.tests import tagged


@tagged('workflow_automation', 'workflow_steps')
class TestWorkflowSteps(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env['ir.model'].search([('model', '=', 'res.partner')], limit=1)
        # Use an existing partner to avoid cross-module NOT NULL constraints
        cls.partner = cls.env['res.partner'].search(
            [('active', '=', True), ('name', '!=', False), ('type', '=', 'contact')], limit=1
        )
        if not cls.partner:
            cls.partner = cls.env['res.partner'].search(
                [('active', '=', True), ('name', '!=', False)], limit=1
            )

    def setUp(self):
        super().setUp()
        self.wf = self.env['wf.automation'].create({
            'name': 'Step Test Workflow',
            'model_id': self.partner_model.id,
            'trigger': 'manual',
            'log_level': 'all',
        })

    def _run(self, step_vals):
        """Helper: create step, run workflow on self.partner, return step + log."""
        step_vals.setdefault('workflow_id', self.wf.id)
        step_vals.setdefault('sequence', 10)
        step = self.env['wf.step'].create(step_vals)
        self.wf.step_ids.filtered(lambda s: s.id != step.id).write({'active': False})
        self.wf._process(self.partner, 'manual')
        log = self.env['wf.execution.log'].search(
            [('workflow_id', '=', self.wf.id)], limit=1, order='id desc'
        )
        return step, log

    # ------------------------------------------------------------------ #
    # stop_workflow                                                        #
    # ------------------------------------------------------------------ #

    def test_stop_workflow_step(self):
        """stop_workflow step produces a 'stopped' step log entry."""
        _, log = self._run({'name': 'Stop', 'step_type': 'stop_workflow'})
        self.assertTrue(log)
        step_log = log.step_log_ids.filtered(lambda l: l.step_type == 'stop_workflow')
        self.assertTrue(step_log)
        self.assertEqual(step_log[0].state, 'stopped')

    # ------------------------------------------------------------------ #
    # create_record                                                        #
    # ------------------------------------------------------------------ #

    def test_create_record_step(self):
        """create_record step creates a new record with mapped field values."""
        tag_model = self.env['ir.model'].search([('model', '=', 'res.partner.category')], limit=1)
        if not tag_model:
            self.skipTest("res.partner.category not available")

        tag_name_field = self.env['ir.model.fields'].search([
            ('model_id', '=', tag_model.id), ('name', '=', 'name')
        ], limit=1)

        step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Create Tag',
            'step_type': 'create_record',
            'create_model_id': tag_model.id,
            'sequence': 10,
        })
        self.env['wf.step.field.mapping'].create({
            'step_id': step.id,
            'field_id': tag_name_field.id,
            'value_type': 'static',
            'static_value': 'WF Created Tag',
        })

        self.wf._process(self.partner, 'manual')

        tag = self.env['res.partner.category'].search([('name', '=', 'WF Created Tag')], limit=1)
        self.assertTrue(tag, "create_record step should have created a partner category")

    # ------------------------------------------------------------------ #
    # update_record                                                        #
    # ------------------------------------------------------------------ #

    def test_update_record_step(self):
        """update_record step writes field values onto the trigger record."""
        comment_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.partner_model.id), ('name', '=', 'comment')
        ], limit=1)
        if not comment_field:
            self.skipTest("res.partner.comment field not available")

        step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Update Comment',
            'step_type': 'update_record',
            'target_record_type': 'trigger',
            'sequence': 10,
        })
        self.env['wf.step.field.mapping'].create({
            'step_id': step.id,
            'field_id': comment_field.id,
            'value_type': 'static',
            'static_value': 'Updated by workflow',
        })

        self.wf._process(self.partner, 'manual')
        self.partner.invalidate_recordset()
        # comment is an HTML field — Odoo wraps plain text in <p> tags
        self.assertIn('Updated by workflow', self.partner.comment or '')

    # ------------------------------------------------------------------ #
    # post_message                                                         #
    # ------------------------------------------------------------------ #

    def test_post_message_step(self):
        """post_message step posts a chatter message on the trigger record."""
        _, log = self._run({
            'name': 'Post Message',
            'step_type': 'post_message',
            'message_post_method': 'note',
            'message_body': '<p>Automated note</p>',
        })
        messages = self.partner.message_ids.filtered(
            lambda m: 'Automated note' in (m.body or '')
        )
        self.assertTrue(messages, "post_message step should have posted a chatter message")

    # ------------------------------------------------------------------ #
    # add_activity                                                         #
    # ------------------------------------------------------------------ #

    def test_add_activity_step(self):
        """add_activity step schedules an activity on the trigger record."""
        activity_type = self.env['mail.activity.type'].search([], limit=1)
        if not activity_type:
            self.skipTest("No activity types configured")

        self._run({
            'name': 'Add Activity',
            'step_type': 'add_activity',
            'activity_type_id': activity_type.id,
            'activity_summary': 'Workflow Test Activity',
            'activity_deadline_days': 3,
            'activity_user_type': 'current_user',
        })
        activities = self.partner.activity_ids.filtered(
            lambda a: a.summary == 'Workflow Test Activity'
        )
        self.assertTrue(activities, "add_activity step should have scheduled an activity")

    # ------------------------------------------------------------------ #
    # conditional_branch                                                   #
    # ------------------------------------------------------------------ #

    def test_conditional_branch_stop_when_fails(self):
        """conditional_branch with branch_action=stop halts workflow when condition fails."""
        # Condition: partner name == 'NEVER_MATCHES'
        branch_step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Branch',
            'step_type': 'conditional_branch',
            'branch_condition_type': 'domain',
            'branch_condition_domain': "[('name', '=', 'NEVER_MATCHES')]",
            'branch_action': 'stop',
            'sequence': 10,
        })
        # This step should NOT run because the branch stops the workflow
        self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Should Not Run',
            'step_type': 'stop_workflow',
            'sequence': 20,
        })

        self.wf._process(self.partner, 'manual')
        log = self.env['wf.execution.log'].search(
            [('workflow_id', '=', self.wf.id)], limit=1, order='id desc'
        )
        self.assertTrue(log)
        branch_log = log.step_log_ids.filtered(lambda l: l.step_id.id == branch_step.id)
        self.assertTrue(branch_log)
        self.assertEqual(branch_log[0].state, 'stopped')

    def test_conditional_branch_continues_when_passes(self):
        """conditional_branch with passing condition continues to next step."""
        branch_step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Branch',
            'step_type': 'conditional_branch',
            'branch_condition_type': 'domain',
            'branch_condition_domain': "[('id', '>', 0)]",  # always true
            'branch_action': 'stop',
            'sequence': 10,
        })
        stop_step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Stop',
            'step_type': 'stop_workflow',
            'sequence': 20,
        })

        self.wf._process(self.partner, 'manual')
        log = self.env['wf.execution.log'].search(
            [('workflow_id', '=', self.wf.id)], limit=1, order='id desc'
        )
        stop_log = log.step_log_ids.filtered(lambda l: l.step_id.id == stop_step.id)
        self.assertTrue(stop_log, "Stop step should have been reached when branch condition passes")

    # ------------------------------------------------------------------ #
    # python_code                                                          #
    # ------------------------------------------------------------------ #

    def test_python_code_step_result(self):
        """python_code step stores 'result' into the named variable."""
        step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Python',
            'step_type': 'python_code',
            'python_code': "result = record.name + ' was here'",
            'store_result_var': 'py_result',
            'sequence': 10,
        })
        self.wf._process(self.partner, 'manual')
        log = self.env['wf.execution.log'].search(
            [('workflow_id', '=', self.wf.id)], limit=1, order='id desc'
        )
        step_log = log.step_log_ids.filtered(lambda l: l.step_id.id == step.id)
        self.assertTrue(step_log)
        self.assertEqual(step_log[0].state, 'success')
        self.assertEqual(step_log[0].stored_variable_name, 'py_result')

    # ------------------------------------------------------------------ #
    # Step conditions                                                      #
    # ------------------------------------------------------------------ #

    def test_step_condition_skip(self):
        """A step whose condition fails is skipped (not stopped)."""
        step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Conditional Step',
            'step_type': 'stop_workflow',
            'condition_type': 'domain',
            'condition_domain': "[('name', '=', 'WILL_NEVER_MATCH')]",
            'on_condition_fail': 'skip',
            'sequence': 10,
        })
        self.wf._process(self.partner, 'manual')
        log = self.env['wf.execution.log'].search(
            [('workflow_id', '=', self.wf.id)], limit=1, order='id desc'
        )
        step_log = log.step_log_ids.filtered(lambda l: l.step_id.id == step.id)
        self.assertTrue(step_log)
        self.assertEqual(step_log[0].state, 'skipped')

    def test_step_condition_stop_workflow(self):
        """A step with on_condition_fail=stop_workflow halts execution."""
        step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Stop on Fail',
            'step_type': 'stop_workflow',
            'condition_type': 'domain',
            'condition_domain': "[('name', '=', 'WILL_NEVER_MATCH')]",
            'on_condition_fail': 'stop_workflow',
            'sequence': 10,
        })
        self.wf._process(self.partner, 'manual')
        log = self.env['wf.execution.log'].search(
            [('workflow_id', '=', self.wf.id)], limit=1, order='id desc'
        )
        step_log = log.step_log_ids.filtered(lambda l: l.step_id.id == step.id)
        self.assertEqual(step_log[0].state, 'stopped')

    # ------------------------------------------------------------------ #
    # Field mapping — value types                                          #
    # ------------------------------------------------------------------ #

    def test_field_mapping_expression_value(self):
        """Field mapping with value_type=expression evaluates Python."""
        website_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.partner_model.id), ('name', '=', 'website')
        ], limit=1)
        if not website_field:
            self.skipTest("res.partner.website field not available")

        step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Set Website',
            'step_type': 'update_record',
            'target_record_type': 'trigger',
            'sequence': 10,
        })
        self.env['wf.step.field.mapping'].create({
            'step_id': step.id,
            'field_id': website_field.id,
            'value_type': 'expression',
            'expression_value': "'https://example.com/' + str(record.id)",
        })

        self.wf._process(self.partner, 'manual')
        self.partner.invalidate_recordset()
        self.assertEqual(
            self.partner.website,
            f'https://example.com/{self.partner.id}'
        )

    def test_field_mapping_record_field_path(self):
        """Field mapping with value_type=record_field reads a field from the trigger record."""
        ref_field = self.env['ir.model.fields'].search([
            ('model_id', '=', self.partner_model.id), ('name', '=', 'website')
        ], limit=1)
        if not ref_field:
            self.skipTest("res.partner.website field not available")

        # Set partner name to a known value for the test
        original_name = self.partner.name

        step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Map Field',
            'step_type': 'update_record',
            'target_record_type': 'trigger',
            'sequence': 10,
        })
        self.env['wf.step.field.mapping'].create({
            'step_id': step.id,
            'field_id': ref_field.id,
            'value_type': 'record_field',
            'record_field_path': 'name',
        })

        self.wf._process(self.partner, 'manual')
        self.partner.invalidate_recordset()
        # website field may auto-prefix with 'http://' — just check the name is present
        self.assertIn(original_name, self.partner.website or '')

    # ------------------------------------------------------------------ #
    # Template rendering                                                   #
    # ------------------------------------------------------------------ #

    def test_render_template_basic(self):
        """_render_template replaces {{expr}} with evaluated values."""
        step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Template Test',
            'step_type': 'stop_workflow',
        })
        ctx = {'record': self.partner, 'env': self.env, 'user': self.env.user}
        result = step._render_template("Hello {{record.name}}!", ctx)
        self.assertEqual(result, f"Hello {self.partner.name}!")

    def test_render_template_no_template_syntax(self):
        """_render_template returns plain strings unchanged."""
        step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Plain Template',
            'step_type': 'stop_workflow',
        })
        result = step._render_template("No template here", {})
        self.assertEqual(result, "No template here")

    def test_render_template_bad_expression_returns_empty(self):
        """_render_template returns empty string for invalid expressions (no crash)."""
        step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Bad Expr',
            'step_type': 'stop_workflow',
        })
        result = step._render_template("{{undefined_var.something}}", {})
        self.assertEqual(result, "")

    def test_render_template_field_selector_placeholders(self):
        """Placeholders inserted by the field selector render, with defaults."""
        step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Field Selector',
            'step_type': 'stop_workflow',
        })
        self.partner.write({'name': 'A & B', 'function': False})
        ctx = step._get_eval_context(self.partner, {})

        # Char / Text fields: {{object.path ||| default}}
        self.assertEqual(
            step._render_template("Hi {{object.name}}", ctx, display=True), "Hi A & B",
        )
        self.assertEqual(
            step._render_template("{{object.function ||| n/a}}", ctx, display=True), "n/a",
        )
        # Html fields: the editor's <t t-out> elements, values escaped
        body = (
            '<p><t t-out="object.name"></t> / '
            '<t t-out="object.function">No job</t></p>'
        )
        self.assertEqual(
            step._render_template(body, ctx, html=True), "<p>A &amp; B / No job</p>",
        )

    def test_render_template_display_formats(self):
        """Dates show as dd/mm/yyyy and records by name in messages."""
        step = self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Formats',
            'step_type': 'stop_workflow',
        })
        self.env.user.tz = 'UTC'
        ctx = {
            'd': datetime.date(2026, 3, 4),
            'dt': datetime.datetime(2026, 3, 4, 5, 6, 7),
            'object': self.partner,
            'format_datetime': step._wf_format_datetime,
        }
        render = step._render_template
        self.assertEqual(render("{{d}}", ctx, display=True), "04/03/2026")
        self.assertEqual(render("{{dt}}", ctx, display=True), "04/03/2026 05:06")
        self.assertEqual(
            render("{{format_datetime(dt, tz='Australia/Sydney')}}", ctx, display=True),
            "04/03/2026 16:06",
        )
        self.assertEqual(render("{{object}}", ctx, display=True), self.partner.display_name)
        # Without display formatting (API calls) values keep their str()
        self.assertEqual(render("{{d}}", ctx), "2026-03-04")

    # ------------------------------------------------------------------ #
    # Trigger sub-workflow                                                 #
    # ------------------------------------------------------------------ #

    def test_trigger_sub_workflow(self):
        """trigger_workflow step runs a sub-workflow on the same record."""
        sub_wf = self.env['wf.automation'].create({
            'name': 'Sub Workflow',
            'model_id': self.partner_model.id,
            'trigger': 'manual',
            'log_level': 'all',
        })

        self.env['wf.step'].create({
            'workflow_id': self.wf.id,
            'name': 'Trigger Sub',
            'step_type': 'trigger_workflow',
            'sub_workflow_id': sub_wf.id,
            'sub_workflow_record_type': 'trigger',
            'sequence': 10,
        })

        self.wf._process(self.partner, 'manual')

        sub_log = self.env['wf.execution.log'].search([('workflow_id', '=', sub_wf.id)])
        self.assertTrue(sub_log, "Sub-workflow should have an execution log")

    # ------------------------------------------------------------------ #
    # send_email recipients                                                #
    # ------------------------------------------------------------------ #

    def _email_step(self, vals):
        vals.update({'workflow_id': self.wf.id, 'name': 'Email', 'step_type': 'send_email'})
        return self.env['wf.step'].create(vals)

    def test_email_to_type_follows_email_type(self):
        """Template emails default to the template's recipients, inline to a field."""
        step = self._email_step({'email_type': 'template'})
        self.assertEqual(step.email_to_type, 'template')
        step.email_type = 'inline'
        self.assertEqual(step.email_to_type, 'field')

    def test_email_inline_rejects_template_recipients(self):
        """An inline email can't use the template's recipients."""
        with self.assertRaises(ValidationError):
            self._email_step({'email_type': 'inline', 'email_to_type': 'template'})

    def test_email_recipients_specific_users(self):
        """Specific Users sends to the selected users' addresses, for any email type."""
        user = self.env.user
        user.partner_id.email = 'wf-user@example.com'
        for email_type in ('template', 'inline'):
            step = self._email_step({
                'email_type': email_type,
                'email_to_type': 'specific_users',
                'email_to_user_ids': [(6, 0, user.ids)],
            })
            self.assertEqual(step.email_to_type, 'specific_users')
            self.assertEqual(step._get_email_recipients(self.partner), ['wf-user@example.com'])

    def test_email_recipients_from_fields(self):
        """Field on Record reads a text field or the users / contacts in a relational field."""
        self.partner.email = 'wf-partner@example.com'
        self.env.user.partner_id.email = 'wf-user@example.com'
        self.partner.user_id = self.env.user
        fields_by_name = {
            f.name: f for f in self.env['ir.model.fields'].search([
                ('model', '=', 'res.partner'), ('name', 'in', ['email', 'user_id', 'child_ids']),
            ])
        }
        cases = [
            ('email', ['wf-partner@example.com']),
            ('user_id', ['wf-user@example.com']),
        ]
        for field_name, expected in cases:
            step = self._email_step({
                'email_type': 'inline',
                'email_to_type': 'field',
                'email_to_field_id': fields_by_name[field_name].id,
            })
            self.assertEqual(step._get_email_recipients(self.partner), expected)

        # A one2many with several contacts sends to all of them
        self.env['res.partner'].create([
            {'name': 'WF Child A', 'parent_id': self.partner.id, 'email': 'a@example.com'},
            {'name': 'WF Child B', 'parent_id': self.partner.id, 'email': 'b@example.com'},
        ])
        step = self._email_step({
            'email_type': 'template',
            'email_to_type': 'field',
            'email_to_field_id': fields_by_name['child_ids'].id,
        })
        recipients = step._get_email_recipients(self.partner)
        self.assertTrue({'a@example.com', 'b@example.com'} <= set(recipients))

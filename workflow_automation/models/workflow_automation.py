# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

import calendar
import datetime as dt
import logging
import traceback
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.tools import safe_eval

_logger = logging.getLogger(__name__)

# Trigger sets — kept as sets for O(1) lookup
CREATE_TRIGGERS = {'on_create', 'on_create_or_write'}
WRITE_TRIGGERS = {'on_write', 'on_create_or_write', 'on_stage_change', 'on_state_change'}
UNLINK_TRIGGERS = {'on_unlink'}

# Weekday index → boolean field name (ISO: Mon=0 … Sun=6)
_WEEKDAY_FIELDS = ['sched_mon', 'sched_tue', 'sched_wed', 'sched_thu',
                   'sched_fri', 'sched_sat', 'sched_sun']


class WfAutomation(models.Model):
    """Workflow automation rule.

    Defines a multi-step workflow that is executed automatically when records
    of the target model are created, written, unlinked, or on a schedule.
    """

    _name = 'wf.automation'
    _description = 'Workflow Automation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # ------------------------------------------------------------------ #
    # Fields                                                               #
    # ------------------------------------------------------------------ #

    name = fields.Char(string='Name', required=True, tracking=True)
    description = fields.Html(string='Description')
    active = fields.Boolean(default=True, tracking=True)

    model_id = fields.Many2one(
        'ir.model',
        string='Model',
        ondelete='cascade',
        domain=[('transient', '=', False)],
        tracking=True,
        help='The model this workflow operates on. Not required for schedule-only workflows.',
    )
    model_name = fields.Char(
        related='model_id.model',
        string='Model Name',
        store=True,
        readonly=True,
    )

    trigger = fields.Selection(
        selection=[
            ('on_create', 'On Create'),
            ('on_write', 'On Write'),
            ('on_create_or_write', 'On Create or Write'),
            ('on_unlink', 'On Delete'),
            ('on_stage_change', 'On Stage Change'),
            ('on_state_change', 'On State Change'),
            ('manual', 'Manual'),
            ('scheduled', 'Scheduled'),
        ],
        string='Trigger',
        required=True,
        default='on_create',
        tracking=True,
    )

    trigger_field_ids = fields.Many2many(
        'ir.model.fields',
        relation='wf_automation_trigger_field_rel',
        column1='automation_id',
        column2='field_id',
        string='Watch Fields',
        domain="[('model_id', '=', model_id)]",
        help='If set, the workflow only fires when one of these fields is modified.',
    )

    filter_domain = fields.Char(
        string='Filter Domain',
        default='[]',
        help='Domain applied after the trigger event. Records not matching are skipped.',
    )
    filter_pre_domain = fields.Char(
        string='Pre-Write Filter Domain',
        default='[]',
        help='Domain evaluated on the record state BEFORE a write. Not checked on create.',
    )
    cron_model_domain = fields.Char(
        string='Scheduled Domain',
        default='[]',
        help='Domain used to select records when this workflow runs on a schedule. '
             'Leave empty (or omit the Model field) to run the workflow once without '
             'iterating over records.',
    )

    # ------------------------------------------------------------------ #
    # Schedule configuration (trigger == 'scheduled')                     #
    # ------------------------------------------------------------------ #

    schedule_type = fields.Selection(
        selection=[
            ('daily',   'Daily'),
            ('weekly',  'Weekly'),
            ('monthly', 'Monthly'),
            ('yearly',  'Yearly'),
        ],
        string='Schedule',
        default='daily',
        help='How often this workflow should run.',
    )
    schedule_interval = fields.Integer(
        string='Run Every',
        default=1,
        help='Repeat interval (e.g. 2 = every 2 days/weeks/months/years).',
    )
    schedule_time = fields.Float(
        string='Run Time (UTC)',
        default=8.0,
        help='Time of day to run, in UTC. Stored as a decimal hour (e.g. 08:30 → 8.5).',
    )

    # Weekly — day checkboxes
    sched_mon = fields.Boolean(string='Mon')
    sched_tue = fields.Boolean(string='Tue')
    sched_wed = fields.Boolean(string='Wed')
    sched_thu = fields.Boolean(string='Thu')
    sched_fri = fields.Boolean(string='Fri')
    sched_sat = fields.Boolean(string='Sat')
    sched_sun = fields.Boolean(string='Sun')

    # Monthly — specific day
    schedule_day_of_month = fields.Integer(
        string='On Day',
        default=1,
        help='Day of the month to run (1–31). If the month has fewer days, '
             'the last day of the month is used instead.',
    )

    # Linked ir.cron — managed automatically
    schedule_cron_id = fields.Many2one(
        'ir.cron',
        string='Scheduled Cron Job',
        ondelete='set null',
        copy=False,
        readonly=True,
        help='Auto-managed cron record that fires this workflow on its schedule.',
    )

    log_level = fields.Selection(
        selection=[
            ('all', 'Log Everything'),
            ('error_only', 'Errors Only'),
            ('none', 'No Logging'),
        ],
        string='Log Level',
        default='all',
        required=True,
    )

    step_ids = fields.One2many(
        'wf.step',
        'workflow_id',
        string='Steps',
        copy=True,
    )
    execution_log_ids = fields.One2many(
        'wf.execution.log',
        'workflow_id',
        string='Execution Logs',
        copy=False,
    )
    execution_log_count = fields.Integer(
        string='Runs',
        compute='_compute_execution_log_count',
    )
    last_run = fields.Datetime(string='Last Run', readonly=True, copy=False)

    connection_ids = fields.One2many(
        'wf.step.connection',
        'workflow_id',
        string='Step Connections',
        copy=False,
    )

    # Canvas viewport state (remembered per workflow)
    canvas_zoom = fields.Float(string='Canvas Zoom', default=1.0)
    canvas_pan_x = fields.Float(string='Canvas Pan X', default=50.0)
    canvas_pan_y = fields.Float(string='Canvas Pan Y', default=50.0)

    # ------------------------------------------------------------------ #
    # Computed fields                                                      #
    # ------------------------------------------------------------------ #

    @api.depends('execution_log_ids')
    def _compute_execution_log_count(self):
        for rec in self:
            rec.execution_log_count = len(rec.execution_log_ids)

    # ------------------------------------------------------------------ #
    # Constraints                                                         #
    # ------------------------------------------------------------------ #

    @api.constrains('model_id', 'trigger')
    def _check_model_required(self):
        for rec in self:
            if rec.trigger != 'scheduled' and not rec.model_id:
                raise models.ValidationError(
                    _('A model is required for "%s" workflows.') % rec.trigger
                )

    @api.constrains('schedule_interval')
    def _check_schedule_interval(self):
        for rec in self:
            if rec.trigger == 'scheduled' and (rec.schedule_interval or 0) < 1:
                raise models.ValidationError(
                    _('Run interval must be at least 1.')
                )

    @api.constrains('schedule_time')
    def _check_schedule_time(self):
        for rec in self:
            if rec.trigger == 'scheduled':
                if not (0.0 <= (rec.schedule_time or 0.0) < 24.0):
                    raise models.ValidationError(
                        _('Run time must be between 00:00 and 23:59.')
                    )

    @api.constrains('schedule_day_of_month')
    def _check_schedule_day_of_month(self):
        for rec in self:
            if rec.trigger == 'scheduled' and rec.schedule_type == 'monthly':
                if not (1 <= (rec.schedule_day_of_month or 1) <= 31):
                    raise models.ValidationError(
                        _('Day of month must be between 1 and 31.')
                    )

    # ------------------------------------------------------------------ #
    # ORM overrides — trigger registry update + cron sync                 #
    # ------------------------------------------------------------------ #

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._update_registry()
        records._sync_cron()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._update_registry()
        # Re-sync cron whenever schedule-related fields change
        _schedule_fields = {
            'trigger', 'active', 'name',
            'schedule_type', 'schedule_interval',
            'schedule_time',
            'sched_mon', 'sched_tue', 'sched_wed', 'sched_thu',
            'sched_fri', 'sched_sat', 'sched_sun',
            'schedule_day_of_month',
        }
        if _schedule_fields & set(vals):
            self._sync_cron()
        return res

    def unlink(self):
        # Delete linked cron records first
        crons = self.mapped('schedule_cron_id').sudo()
        res = super().unlink()
        if crons:
            crons.unlink()
        self._update_registry()
        return res

    # ------------------------------------------------------------------ #
    # Hook registration (base.automation pattern)                         #
    # ------------------------------------------------------------------ #

    @api.model
    def _register_hook(self):
        """Patch model methods to intercept create/write/unlink and run matching workflows.

        Follows the same closure-based patching pattern used by base.automation so that
        each patch wraps the previous one rather than replacing it wholesale.
        """

        def make_create():
            """Return a patched create() that fires CREATE_TRIGGERS workflows."""
            @api.model_create_multi
            def create(self, vals_list, **kw):
                automations = self.env['wf.automation']._get_actions(self, CREATE_TRIGGERS)
                if not automations:
                    return create.origin(self, vals_list, **kw)
                records = create.origin(self.with_env(automations.env), vals_list, **kw)
                for automation in automations.with_context(old_values=None):
                    automation._process(automation._filter_post(records), 'on_create')
                return records.with_env(self.env)
            return create

        def make_write():
            """Return a patched write() that fires WRITE_TRIGGERS workflows."""
            def write(self, vals, **kw):
                automations = self.env['wf.automation']._get_actions(self, WRITE_TRIGGERS)
                if not (automations and self):
                    return write.origin(self, vals, **kw)
                records = self.with_env(automations.env).filtered('id')
                # capture pre-write filter results
                pre = {a: a._filter_pre(records) for a in automations}
                # capture old field values for watched-field checks
                watched_fields = set()
                for a in automations:
                    watched_fields.update(a.sudo().trigger_field_ids.mapped('name'))
                write_fields = set(vals.keys())
                relevant_fields = (watched_fields | write_fields) & set(records._fields)
                old_values = {
                    record.id: {
                        fname: record[fname]
                        for fname in relevant_fields
                        if fname in record._fields and record._fields[fname].store
                    }
                    for record in records
                }
                write.origin(self.with_env(automations.env), vals, **kw)
                for automation in automations.with_context(old_values=old_values):
                    automation._process(automation._filter_post(pre[automation]), 'on_write')
                return True
            return write

        def make_unlink():
            """Return a patched unlink() that fires UNLINK_TRIGGERS workflows."""
            def unlink(self, **kw):
                automations = self.env['wf.automation']._get_actions(self, UNLINK_TRIGGERS)
                records = self.with_env(automations.env)
                for automation in automations:
                    automation._process(automation._filter_post(records), 'on_unlink')
                return unlink.origin(self, **kw)
            return unlink

        patched_models = defaultdict(set)

        def patch(model, name, method):
            """Patch method *name* on *model*, skipping if already patched in this run."""
            if model not in patched_models[name]:
                patched_models[name].add(model)
                ModelClass = model.env.registry[model._name]
                method.origin = getattr(ModelClass, name)
                setattr(ModelClass, name, method)

        for automation in self.with_context({}).search([]):
            if not automation.model_name:
                # Modelless scheduled workflows don't need ORM hooks
                continue
            Model = self.env.get(automation.model_name)
            if Model is None:
                _logger.warning(
                    "wf.automation '%s' (ID %d) references unknown model '%s'",
                    automation.name,
                    automation.id,
                    automation.model_name,
                )
                continue

            trigger = automation.trigger
            if trigger in CREATE_TRIGGERS:
                patch(Model, 'create', make_create())
            if trigger in WRITE_TRIGGERS:
                patch(Model, 'write', make_write())
            if trigger in UNLINK_TRIGGERS:
                patch(Model, 'unlink', make_unlink())

    @api.model
    def _unregister_hook(self):
        """Remove all patches installed by _register_hook()."""
        for Model in self.env.registry.values():
            for name in ('create', 'write', 'unlink'):
                try:
                    delattr(Model, name)
                except AttributeError:
                    pass

    def _update_registry(self):
        """Unregister existing patches, re-register, and invalidate the registry."""
        if self.env.registry.ready and not self.env.context.get('import_file'):
            self._unregister_hook()
            self._register_hook()
            self.env.registry.registry_invalidated = True

    # ------------------------------------------------------------------ #
    # Action retrieval & filtering                                        #
    # ------------------------------------------------------------------ #

    @api.model
    def _get_actions(self, records, triggers):
        """Return active wf.automation rules matching the model and triggers.

        If the anti-recursion context key is absent it is initialised here so
        that every patched method starts with a clean guard dict.
        """
        if '__wf_action_done' not in self.env.context:
            self = self.with_context(__wf_action_done={})
        domain = [
            ('model_name', '=', records._name),
            ('trigger', 'in', list(triggers)),
        ]
        automations = self.with_context(active_test=True).sudo().search(domain)
        return automations.with_env(self.env)

    def _filter_post(self, records):
        """Return the subset of *records* that match ``filter_domain``."""
        self.ensure_one()
        self_sudo = self.sudo()
        if self_sudo.filter_domain and self_sudo.filter_domain.strip() not in ('', '[]') and records:
            try:
                domain = safe_eval.safe_eval(
                    self_sudo.filter_domain,
                    self._get_eval_context(),
                )
                records = records.sudo().filtered_domain(domain).with_env(records.env)
            except Exception:
                _logger.exception(
                    "wf.automation '%s' — error evaluating filter_domain '%s'",
                    self_sudo.name,
                    self_sudo.filter_domain,
                )
        return records

    def _filter_pre(self, records):
        """Return the subset of *records* that match ``filter_pre_domain`` (pre-write state)."""
        self.ensure_one()
        self_sudo = self.sudo()
        if self_sudo.filter_pre_domain and self_sudo.filter_pre_domain.strip() not in ('', '[]') and records:
            try:
                domain = safe_eval.safe_eval(
                    self_sudo.filter_pre_domain,
                    self._get_eval_context(),
                )
                records = records.sudo().filtered_domain(domain).with_env(records.env)
            except Exception:
                _logger.exception(
                    "wf.automation '%s' — error evaluating filter_pre_domain '%s'",
                    self_sudo.name,
                    self_sudo.filter_pre_domain,
                )
        return records

    def _check_trigger_fields(self, record):
        """Return True if any watched field changed on *record* (or if no watch-list is set)."""
        self.ensure_one()
        self_sudo = self.sudo()
        if not self_sudo.trigger_field_ids:
            return True
        old_values = self.env.context.get('old_values')
        if old_values is None:
            # create path — all fields considered new
            return True
        old_vals = old_values.get(record.id, {})

        def differ(name):
            return name in old_vals and record[name] != old_vals[name]

        return any(differ(field.name) for field in self_sudo.trigger_field_ids)

    # ------------------------------------------------------------------ #
    # Process                                                              #
    # ------------------------------------------------------------------ #

    def _process(self, records, trigger_type):
        """Run this workflow on *records*, respecting the anti-recursion guard.

        Args:
            records: Recordset of the trigger model.
            trigger_type: String label of the trigger event (e.g. 'on_create').
        """
        self.ensure_one()
        if not records:
            return

        # ---- anti-recursion guard ----
        action_done = self.env.context.get('__wf_action_done', {})
        done_ids = action_done.get(self.id, set())
        new_records = records.filtered(lambda r: r.id not in done_ids)
        if not new_records:
            return

        # Filter by trigger fields BEFORE marking as done
        new_records = new_records.filtered(self._check_trigger_fields)
        if not new_records:
            return

        updated_done = dict(action_done)
        updated_done[self.id] = done_ids | set(new_records.ids)
        env = self.env(context=dict(self.env.context, __wf_action_done=updated_done))
        self = self.with_env(env)
        new_records = new_records.with_env(env)

        for record in new_records:
            try:
                self._execute_workflow_on_record(record, trigger_type)
            except Exception:
                _logger.exception(
                    "wf.automation '%s' (ID %d) — unhandled error on record %s #%d",
                    self.sudo().name,
                    self.id,
                    record._name,
                    record.id,
                )

    def _execute_workflow_on_record(self, record, trigger_type):
        """Create an execution log, run all active steps in sequence, finalise the log."""
        self.ensure_one()
        import time as _time

        log_level = self.sudo().log_level
        should_log = log_level in ('all', 'error_only')

        # Build run context
        run_context = {
            'variables': {},
            'env': self.env,
            'workflow': self,
            'trigger_record': record,
            'trigger_type': trigger_type,
            'old_values': self.env.context.get('old_values', {}),
            'execution_log': self.env['wf.execution.log'],  # placeholder
        }

        # Create execution log
        execution_log = self.env['wf.execution.log']
        if should_log:
            try:
                record_name = record.sudo().display_name or str(record.id)
            except Exception:
                record_name = str(record.id)
            execution_log = self.env['wf.execution.log'].sudo().create({
                'workflow_id': self.id,
                'trigger_model': record._name,
                'trigger_record_id': record.id,
                'trigger_record_name': record_name,
                'trigger_type': trigger_type,
                'state': 'running',
            })
            run_context['execution_log'] = execution_log

        start_ts = _time.time()
        overall_state = 'success'
        error_message = False
        counters = {'total': 0, 'executed': 0, 'skipped': 0}

        active_steps = self.sudo().step_ids.filtered('active').sorted('sequence')
        connections = self.sudo().connection_ids

        try:
            if connections:
                self._execute_graph_steps(active_steps, connections, record, run_context, counters)
            else:
                # Sequence-based execution (no canvas connections defined)
                for step in active_steps:
                    counters['total'] += 1
                    result = step._execute(record, run_context)
                    if result == 'skip':
                        counters['skipped'] += 1
                    elif result == 'stop':
                        counters['executed'] += 1
                        break
                    elif result == 'error':
                        counters['executed'] += 1
                        overall_state = 'partial'
                    else:
                        counters['executed'] += 1
        except Exception:
            overall_state = 'error'
            error_message = traceback.format_exc()
            _logger.exception(
                "wf.automation '%s' — fatal error during execution on %s #%d",
                self.sudo().name,
                record._name,
                record.id,
            )

        end_ts = _time.time()
        duration_ms = int((end_ts - start_ts) * 1000)

        # Update last_run on the workflow
        self.sudo().write({'last_run': fields.Datetime.now()})

        # Finalise execution log
        if execution_log:
            # For error_only log level, delete the log if it was a success
            if log_level == 'error_only' and overall_state == 'success':
                execution_log.sudo().unlink()
            else:
                execution_log.sudo().write({
                    'state': overall_state,
                    'ended_at': fields.Datetime.now(),
                    'duration_ms': duration_ms,
                    'error_message': error_message,
                    'steps_total': counters['total'],
                    'steps_executed': counters['executed'],
                    'steps_skipped': counters['skipped'],
                })

    def _execute_graph_steps(self, all_steps, connections, record, run_context, counters):
        """BFS graph traversal of workflow steps following explicit connections.

        Entry points are steps with no incoming connections.  After each step
        the engine evaluates outgoing connections in sequence order and adds
        target steps whose condition matches to the processing queue.
        """
        self.ensure_one()
        step_map = {s.id: s for s in all_steps}

        # Build adjacency structures
        outgoing = {s.id: [] for s in all_steps}
        incoming_count = {s.id: 0 for s in all_steps}
        for conn in connections:
            fid = conn.from_step_id.id
            tid = conn.to_step_id.id
            if fid in outgoing:
                outgoing[fid].append(conn)
            if tid in incoming_count:
                incoming_count[tid] = incoming_count.get(tid, 0) + 1

        # Entry steps: no incoming connections, in sequence order
        entry_steps = [s for s in all_steps if incoming_count.get(s.id, 0) == 0]
        if not entry_steps and all_steps:
            entry_steps = [all_steps[0]]

        visited = set()
        queue = list(entry_steps)

        while queue:
            step = queue.pop(0)
            if step.id in visited:
                continue
            visited.add(step.id)

            counters['total'] += 1
            result = step._execute(record, run_context)

            _logger.debug(
                "wf.automation graph — step '%s' (id=%d, type=%s) → signal='%s'",
                step.sudo().name, step.id, step.sudo().step_type, result,
            )

            if result == 'skip':
                counters['skipped'] += 1
                # Skipped steps still propagate to their outgoing connections

            elif result == 'stop':
                # stop_workflow step (or any step explicitly halting execution):
                # clear the queue and exit the graph traversal entirely.
                counters['executed'] += 1
                queue.clear()
                return

            elif result == 'blocked':
                # conditional_branch whose condition was NOT met.
                # Do NOT clear the queue — other parallel branches may have
                # already queued downstream steps that must still execute.
                # Simply skip connection-following for this branch.
                counters['executed'] += 1
                _logger.debug(
                    "wf.automation graph — branch '%s' blocked; queue still has %d item(s)",
                    step.sudo().name, len(queue),
                )
                continue  # skip the connection-following loop below

            elif result == 'error':
                counters['executed'] += 1
                continue  # don't follow connections from errored step

            else:
                counters['executed'] += 1

            # Follow matching outgoing connections (ordered by sequence)
            step_conns = outgoing.get(step.id, [])
            _logger.debug(
                "wf.automation graph — step '%s' has %d outgoing connection(s)",
                step.sudo().name, len(step_conns),
            )
            for conn in sorted(step_conns, key=lambda c: (c.sequence, c.id)):
                tid = conn.to_step_id.id
                if tid not in visited and tid in step_map:
                    passes = conn.evaluate(record, run_context)
                    _logger.debug(
                        "wf.automation graph — connection %d (%s → %s, type=%s) evaluates=%s",
                        conn.id,
                        step.sudo().name,
                        step_map[tid].sudo().name if tid in step_map else tid,
                        conn.condition_type,
                        passes,
                    )
                    if passes:
                        queue.append(step_map[tid])

    def action_open_canvas(self):
        """Open the visual canvas editor for this workflow."""
        self.ensure_one()
        # Pass workflow_id in both `params` (preferred by Odoo client actions) and
        # `context` (fallback).  Do NOT spread self.env.context — it can contain
        # non-serialisable values and ORM cursor references that break JSON encoding.
        return {
            'type': 'ir.actions.client',
            'tag': 'workflow_automation.canvas',
            'name': f'Canvas — {self.name}',
            'params': {'workflow_id': self.id},
            'context': {'workflow_id': self.id},
        }

    # ------------------------------------------------------------------ #
    # Eval context                                                         #
    # ------------------------------------------------------------------ #

    def _get_eval_context(self, record=None, run_context=None):
        """Build the safe_eval context used for domain/Python evaluation."""
        ctx = {
            'datetime': safe_eval.datetime,
            'dateutil': safe_eval.dateutil,
            'time': safe_eval.time,
            'uid': self.env.uid,
            'user': self.env.user,
            'env': self.env,
        }
        if self:
            self.ensure_one()
            ctx['workflow'] = self
        if record is not None:
            ctx['record'] = record
            ctx['model'] = record
        if run_context is not None:
            ctx.update(run_context.get('variables', {}))
            ctx['variables'] = run_context.get('variables', {})
            ctx['old_values'] = run_context.get('old_values', {})
        return ctx

    # ------------------------------------------------------------------ #
    # Schedule management — individual ir.cron per workflow               #
    # ------------------------------------------------------------------ #

    def _get_cron_nextcall(self):
        """Return the next UTC datetime this workflow should fire.

        For daily schedules the cron interval handles recurrence natively.
        For weekly / monthly / yearly the cron runs every day and the
        ``_should_run_now`` guard method decides whether to actually execute.
        """
        self.ensure_one()
        t = max(0.0, min(23.9999, self.schedule_time or 8.0))
        hour = int(t)
        minute = round((t - hour) * 60)
        now = dt.datetime.utcnow()

        # Candidate: today at the target time
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += dt.timedelta(days=1)

        stype = self.schedule_type or 'daily'

        if stype == 'weekly':
            # Advance to the earliest selected weekday on or after candidate
            selected = [i for i, f in enumerate(_WEEKDAY_FIELDS) if getattr(self, f, False)]
            if not selected:
                selected = [0]  # fallback to Monday
            for offset in range(7):
                check = candidate + dt.timedelta(days=offset)
                if check.weekday() in selected:
                    candidate = check
                    break

        elif stype == 'monthly':
            day = max(1, min(31, self.schedule_day_of_month or 1))
            # Try this or next month
            for _ in range(2):
                last_day = calendar.monthrange(candidate.year, candidate.month)[1]
                target_day = min(day, last_day)
                candidate = candidate.replace(day=target_day)
                if candidate > now:
                    break
                # Advance one month
                if candidate.month == 12:
                    candidate = candidate.replace(year=candidate.year + 1, month=1, day=1)
                else:
                    candidate = candidate.replace(month=candidate.month + 1, day=1)

        # yearly: let the 12-month interval handle it; nextcall is just tomorrow

        return candidate

    def _get_cron_interval(self):
        """Return (interval_number, interval_type) for the ir.cron record."""
        self.ensure_one()
        stype = self.schedule_type or 'daily'
        n = max(1, self.schedule_interval or 1)

        if stype == 'daily':
            return n, 'days'
        elif stype == 'weekly':
            # Run daily; _should_run_now enforces the weekday + week-count guard
            return 1, 'days'
        elif stype == 'monthly':
            # Run daily; _should_run_now enforces the day-of-month + month guard
            return 1, 'days'
        elif stype == 'yearly':
            # Run daily; _should_run_now enforces the year-count guard
            return 1, 'days'
        return 1, 'days'

    def _sync_cron(self):
        """Create, update, or delete the ir.cron record tied to each workflow."""
        Cron = self.env['ir.cron'].sudo()
        wf_model_id = self.env['ir.model'].sudo().search(
            [('model', '=', 'wf.automation')], limit=1
        ).id

        for workflow in self:
            is_scheduled = (workflow.trigger == 'scheduled' and workflow.active)

            if not is_scheduled:
                # Remove any existing cron
                if workflow.schedule_cron_id:
                    try:
                        workflow.schedule_cron_id.sudo().unlink()
                    except Exception:
                        pass
                    workflow.sudo().write({'schedule_cron_id': False})
                continue

            nextcall = workflow._get_cron_nextcall()
            interval_number, interval_type = workflow._get_cron_interval()

            cron_vals = {
                'name': 'Workflow Engine: %s' % workflow.name,
                'model_id': wf_model_id,
                'state': 'code',
                'code': 'model._cron_run_workflow(%d)' % workflow.id,
                'interval_number': interval_number,
                'interval_type': interval_type,
                'nextcall': nextcall,
                'active': True,
                'priority': 10,
            }

            if workflow.schedule_cron_id:
                workflow.schedule_cron_id.sudo().write(cron_vals)
                _logger.info(
                    "wf.automation '%s' — updated schedule cron (id=%d)",
                    workflow.name, workflow.schedule_cron_id.id,
                )
            else:
                cron = Cron.create(cron_vals)
                workflow.sudo().with_context(no_cron_sync=True).write(
                    {'schedule_cron_id': cron.id}
                )
                _logger.info(
                    "wf.automation '%s' — created schedule cron (id=%d, nextcall=%s)",
                    workflow.name, cron.id, nextcall,
                )

    def _should_run_now(self):
        """Return True if this workflow is due to execute right now.

        Called from the individual cron just before execution to enforce
        weekday, day-of-month, and interval guards that the cron itself
        cannot handle natively.
        """
        self.ensure_one()
        now = dt.datetime.utcnow()
        stype = self.schedule_type or 'daily'
        interval = max(1, self.schedule_interval or 1)
        last = self.last_run  # UTC datetime or False

        if stype == 'daily':
            # Cron interval handles recurrence; just check we haven't already
            # run today at or after the scheduled time (guards against cron overlap).
            if last and last.date() == now.date():
                t = max(0.0, min(23.9999, self.schedule_time or 8.0))
                sched_minutes = int(t) * 60 + round((t - int(t)) * 60)
                last_minutes = last.hour * 60 + last.minute
                if last_minutes >= sched_minutes:
                    return False
            return True

        elif stype == 'weekly':
            selected = [i for i, f in enumerate(_WEEKDAY_FIELDS) if getattr(self, f, False)]
            if not selected:
                selected = [0]
            if now.weekday() not in selected:
                return False
            if last:
                days_since = (now.date() - last.date()).days
                if days_since < interval * 7:
                    return False
            return True

        elif stype == 'monthly':
            target_day = max(1, min(31, self.schedule_day_of_month or 1))
            last_day_of_month = calendar.monthrange(now.year, now.month)[1]
            effective_day = min(target_day, last_day_of_month)
            if now.day != effective_day:
                return False
            if last:
                months_since = (now.year - last.year) * 12 + (now.month - last.month)
                if months_since < interval:
                    return False
            return True

        elif stype == 'yearly':
            if last:
                if (now.year - last.year) < interval:
                    return False
            return True

        return True

    # ------------------------------------------------------------------ #
    # Scheduled trigger execution                                         #
    # ------------------------------------------------------------------ #

    @api.model
    def _cron_run_workflow(self, workflow_id):
        """Entry point called by each workflow's individual ir.cron record."""
        workflow = self.browse(workflow_id).sudo()
        if not workflow.exists():
            _logger.warning(
                "wf.automation._cron_run_workflow: workflow id=%d not found", workflow_id
            )
            return
        if not workflow.active or workflow.trigger != 'scheduled':
            return

        if not workflow._should_run_now():
            _logger.debug(
                "wf.automation '%s' — schedule guard: skipping (not due yet)",
                workflow.name,
            )
            return

        _logger.info(
            "wf.automation '%s' — running scheduled workflow (type=%s, interval=%d)",
            workflow.name, workflow.schedule_type, workflow.schedule_interval or 1,
        )

        try:
            if workflow.model_id:
                workflow._run_scheduled_with_model()
            else:
                workflow._run_scheduled_modelless()
        except Exception:
            _logger.exception(
                "wf.automation '%s' — unhandled error during scheduled execution",
                workflow.name,
            )

    def _run_scheduled_with_model(self):
        """Run a scheduled workflow that has a model — iterate matching records."""
        self.ensure_one()
        try:
            domain = safe_eval.safe_eval(
                self.cron_model_domain or '[]',
                self._get_eval_context(),
            )
        except Exception:
            _logger.exception(
                "wf.automation '%s' — error evaluating cron_model_domain", self.name
            )
            domain = []

        Model = self.env.get(self.model_name)
        if Model is None:
            _logger.warning(
                "wf.automation '%s' — scheduled model '%s' not found",
                self.name, self.model_name,
            )
            return

        records = Model.search(domain)
        _logger.info(
            "wf.automation '%s' — scheduled run on %d %s record(s)",
            self.name, len(records), self.model_name,
        )
        self._process(records, 'scheduled')

    def _run_scheduled_modelless(self):
        """Run a scheduled workflow that has no model — executes once, no trigger record."""
        self.ensure_one()
        _logger.info(
            "wf.automation '%s' — modelless scheduled run", self.name,
        )
        import time as _time

        log_level = self.log_level
        should_log = log_level in ('all', 'error_only')

        run_context = {
            'variables': {},
            'env': self.env,
            'workflow': self,
            'trigger_record': None,
            'trigger_type': 'scheduled',
            'old_values': {},
            'execution_log': self.env['wf.execution.log'],
        }

        execution_log = self.env['wf.execution.log']
        if should_log:
            execution_log = self.env['wf.execution.log'].sudo().create({
                'workflow_id': self.id,
                'trigger_model': '(none)',
                'trigger_record_id': 0,
                'trigger_record_name': '(scheduled — no record)',
                'trigger_type': 'scheduled',
                'state': 'running',
            })
            run_context['execution_log'] = execution_log

        start_ts = _time.time()
        overall_state = 'success'
        error_message = False
        counters = {'total': 0, 'executed': 0, 'skipped': 0}

        active_steps = self.sudo().step_ids.filtered('active').sorted('sequence')
        connections = self.sudo().connection_ids

        try:
            if connections:
                self._execute_graph_steps(active_steps, connections, None, run_context, counters)
            else:
                for step in active_steps:
                    counters['total'] += 1
                    result = step._execute_modelless(run_context)
                    if result == 'skip':
                        counters['skipped'] += 1
                    elif result in ('stop', 'blocked'):
                        counters['executed'] += 1
                        break
                    elif result == 'error':
                        counters['executed'] += 1
                        overall_state = 'partial'
                    else:
                        counters['executed'] += 1
        except Exception:
            overall_state = 'error'
            error_message = traceback.format_exc()
            _logger.exception(
                "wf.automation '%s' — fatal error during modelless scheduled execution",
                self.name,
            )

        duration_ms = int((_time.time() - start_ts) * 1000)
        self.sudo().write({'last_run': fields.Datetime.now()})

        if execution_log:
            if log_level == 'error_only' and overall_state == 'success':
                execution_log.sudo().unlink()
            else:
                execution_log.sudo().write({
                    'state': overall_state,
                    'ended_at': fields.Datetime.now(),
                    'duration_ms': duration_ms,
                    'error_message': error_message,
                    'steps_total': counters['total'],
                    'steps_executed': counters['executed'],
                    'steps_skipped': counters['skipped'],
                })

    @api.model
    def _cron_run_scheduled_workflows(self):
        """Master cron entry-point — runs all active scheduled workflows that are due.

        Delegates to ``_cron_run_workflow`` for each workflow so that the
        ``_should_run_now()`` schedule guard applies, preventing double-execution
        when an individual per-workflow cron fires in the same window.
        """
        workflows = self.with_context(active_test=True).search([
            ('trigger', '=', 'scheduled'),
        ])
        for workflow in workflows:
            try:
                self._cron_run_workflow(workflow.id)
            except Exception:
                _logger.exception(
                    "wf.automation '%s' — error during scheduled execution",
                    workflow.name,
                )

    # ------------------------------------------------------------------ #
    # UI actions                                                           #
    # ------------------------------------------------------------------ #

    def action_view_logs(self):
        """Return an action opening the execution logs for this workflow."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Execution Logs — %s') % self.name,
            'res_model': 'wf.execution.log',
            'view_mode': 'list,form',
            'domain': [('workflow_id', '=', self.id)],
            'context': {'default_workflow_id': self.id},
        }

    def action_run_manual(self):
        """Test-run this workflow.

        * Record-based triggers (on_create, on_write, etc.) — open the
          record-picker wizard so the user can choose a test record.
        * Manual / Scheduled triggers — execute immediately without a dialog
          and return a success notification.
        """
        self.ensure_one()

        # Triggers that require a specific test record
        _RECORD_TRIGGERS = frozenset({
            'on_create', 'on_write', 'on_create_or_write',
            'on_unlink', 'on_stage_change', 'on_state_change',
        })

        if self.trigger in _RECORD_TRIGGERS:
            # Open the wizard for the user to select a test record
            return {
                'type': 'ir.actions.act_window',
                'name': _('Test Workflow — Pick a Record'),
                'res_model': 'wf.manual.run.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_workflow_id': self.id},
            }

        # ── Immediate execution for manual / scheduled ────────────────── #
        try:
            if self.trigger == 'scheduled':
                # Run the scheduled logic directly, bypassing the schedule guard
                if self.model_id:
                    self._run_scheduled_with_model()
                else:
                    self._run_scheduled_modelless()
            else:
                # manual trigger — run against records matching filter_domain
                if self.model_id:
                    try:
                        domain = safe_eval.safe_eval(
                            self.filter_domain or '[]',
                            self._get_eval_context(),
                        )
                    except Exception:
                        domain = []
                    Model = self.env.get(self.model_name)
                    records = Model.search(domain) if Model else self.env['res.lang'].browse()
                    if records:
                        self._process(records, 'manual')
                    else:
                        # No matching records — still exercise the steps modellessly
                        self._run_scheduled_modelless()
                else:
                    self._run_scheduled_modelless()
        except Exception:
            _logger.exception(
                "wf.automation '%s' — error during manual test run", self.name
            )
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Test Failed'),
                    'message': _(
                        'An error occurred running "%s". '
                        'Check the server log and Runs log for details.'
                    ) % self.name,
                    'sticky': True,
                    'type': 'danger',
                },
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Test Run Complete'),
                'message': _(
                    'Workflow "%s" was executed. '
                    'Check the Runs log for step-by-step results.'
                ) % self.name,
                'sticky': False,
                'type': 'success',
            },
        }

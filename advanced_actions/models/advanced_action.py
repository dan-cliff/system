from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError

# Fields org_structure adds to primary models (see CLAUDE.md > Organisation structure).
ORG_FIELD_NAMES = ('org_division_id', 'org_business_unit_id', 'org_location_id', 'org_department_id')
# Days are turned into a Due At time at the end of the working day.
DUE_HOUR = 17


class AdvancedAction(models.Model):
    """One action, whichever app raised it.

    Apps that need actions store them here instead of in a model of their
    own: a bridge module adds the link to the app's record (e.g.
    ``incident_id``), lists it in ``_action_sources`` and adds its app to
    ``source_app``. The app's own Actions menu opens this model filtered on
    its app, and the filter can be removed to see every action.
    """
    _name = 'advanced.action'
    _description = 'Action'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, date_deadline, id desc'
    # Actions are raised from records of different apps; create() copies the
    # Organisation of whichever record that is (see _action_sources).
    _org_parent_field = False

    name = fields.Char(string='Title', required=True, tracking=True)
    description = fields.Html()
    active = fields.Boolean(default=True)
    user_ids = fields.Many2many(
        'res.users', 'advanced_action_res_users_rel', 'action_id', 'user_id',
        string='Assigned To', tracking=True, domain=[('share', '=', False)],
        default=lambda self: self.env.user,
        help='Any one of these users can complete the action. To give several users '
             'an action each, use Duplicate for Users.',
    )
    date_deadline = fields.Datetime(string='Due At', tracking=True, index=True)
    # Technical workflow state: the buttons, filters and notifications depend on it.
    state = fields.Selection(
        [('open', 'Open'), ('in_progress', 'In Progress'), ('done', 'Done'), ('cancelled', 'Cancelled')],
        string='Status', default='open', required=True, tracking=True, copy=False, index=True,
    )
    # Odoo's star widget.
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'Important'), ('2', 'Very Important'), ('3', 'Critical')],
        default='0',
    )
    date_done = fields.Datetime(string='Completed At', readonly=True, copy=False)
    tag_ids = fields.Many2many('advanced.action.tag', string='Tags')
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company,
    )
    is_overdue = fields.Boolean(string='Overdue', compute='_compute_is_overdue', search='_search_is_overdue')

    # Required Checklist: the template to complete, and the checklist filled in
    # for this action. Completing that checklist completes the action.
    checklist_template_id = fields.Many2one(
        'checklist.template', string='Required Checklist', tracking=True, ondelete='restrict',
    )
    checklist_id = fields.Many2one(
        'checklist.checklist', string='Checklist', copy=False, ondelete='set null', index='btree_not_null',
    )
    checklist_state = fields.Selection(related='checklist_id.state', string='Checklist Status')

    # Where the action comes from. Technical: each app's filter and access
    # rules depend on it, and bridge modules add their app.
    source_app = fields.Selection(
        [('general', 'Actions'), ('checklists', 'Checklists')],
        string='App', default='general', required=True, index=True,
    )
    source_checklist_id = fields.Many2one(
        'checklist.checklist', string='Raised From Checklist', ondelete='cascade', index='btree_not_null',
    )
    source_display = fields.Char(string='Raised From', compute='_compute_source_display')

    # Duplicate for Users: copies given to one user each.
    origin_id = fields.Many2one(
        'advanced.action', string='Duplicated From', copy=False, index='btree_not_null', ondelete='set null',
    )
    copy_ids = fields.One2many('advanced.action', 'origin_id', string='Copies')
    copy_count = fields.Integer(compute='_compute_copy_count')

    # Notifications already sent (see advanced.action.notification).
    due_soon_notified = fields.Boolean(copy=False)
    overdue_notified = fields.Boolean(copy=False)

    # ── Sources ──────────────────────────────────────────────────────────
    @api.model
    def _action_sources(self):
        """(link field, app) pairs to the record an action is raised from, in
        order. Bridge modules add theirs."""
        return [('source_checklist_id', 'checklists')]

    def _action_source_parent(self, field_name, record):
        """The record whose Company and Organisation a new action raised from
        ``record`` (through ``field_name``) takes."""
        return record

    def _action_source(self):
        """(field, linked record) of the record this action was raised from."""
        self.ensure_one()
        for field_name, _app in self._action_sources():
            if self[field_name]:
                return field_name, self[field_name]
        return False, False

    def _compute_source_display(self):
        for action in self:
            field_name, record = action._action_source()
            action.source_display = record.display_name if record else False

    def _compute_copy_count(self):
        for action in self:
            action.copy_count = len(action.copy_ids)

    @api.depends('state', 'date_deadline')
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for action in self:
            action.is_overdue = bool(
                action.state in ('open', 'in_progress') and action.date_deadline and action.date_deadline < now
            )

    def _search_is_overdue(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(self.env._('Unsupported search on Overdue.'))
        domain = [('state', 'in', ('open', 'in_progress')), ('date_deadline', '<', fields.Datetime.now())]
        return domain if (operator == '=') == value else ['!', '&'] + domain

    # ── Create / write ───────────────────────────────────────────────────
    def _source_link_from_vals(self, vals):
        for field_name, app in self._action_sources():
            if vals.get(field_name):
                return field_name, app
        return False, False

    def _source_values(self, field_name, record_id):
        """Company and Organisation of the record an action is raised from."""
        record = self.env[self._fields[field_name].comodel_name].sudo().browse(record_id).exists()
        parent = record and self._action_source_parent(field_name, record)
        if not parent:
            return {}
        values = {}
        if 'company_id' in parent._fields and parent.company_id:
            values['company_id'] = parent.company_id.id
        if all(name in self._fields and name in parent._fields for name in ORG_FIELD_NAMES):
            values.update({name: parent[name].id for name in ORG_FIELD_NAMES})
        return values

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        field_name, app = self._source_link_from_vals(res)
        if field_name:
            res['source_app'] = app
            res.update({
                name: value for name, value in self._source_values(field_name, res[field_name]).items()
                if name in fields_list
            })
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            field_name, app = self._source_link_from_vals(vals)
            if field_name:
                vals['source_app'] = app
                source = self._source_values(field_name, vals[field_name])
                if any(vals.get(name) for name in ORG_FIELD_NAMES):
                    source = {name: value for name, value in source.items() if name not in ORG_FIELD_NAMES}
                for name, value in source.items():
                    vals.setdefault(name, value)
        actions = super().create(vals_list)
        actions._notify('assigned', partners_by_action={
            action: action.user_ids.partner_id for action in actions
        })
        return actions

    def write(self, vals):
        field_name, app = self._source_link_from_vals(vals)
        if field_name:
            vals['source_app'] = app
        if vals.get('state') == 'done':
            self._check_checklist_completed()
            vals.setdefault('date_done', fields.Datetime.now())
        elif vals.get('state') in ('open', 'in_progress', 'cancelled'):
            vals.setdefault('date_done', False)
        if 'date_deadline' in vals:
            vals.update(due_soon_notified=False, overdue_notified=False)
        before = {action: action.user_ids for action in self} if 'user_ids' in vals else {}
        old_states = {action: action.state for action in self} if 'state' in vals else {}
        res = super().write(vals)
        if before:
            self._notify('assigned', partners_by_action={
                action: (action.user_ids - before[action]).partner_id for action in self
            })
        if old_states:
            for state, event in (('done', 'done'), ('cancelled', 'cancelled')):
                changed = self.filtered(lambda a: a.state == state and old_states[a] != state)
                changed._notify(event)
        return res

    def _check_checklist_completed(self):
        for action in self:
            if action.checklist_template_id and action.checklist_id.state != 'done':
                raise UserError(self.env._(
                    'Complete the required checklist "%(checklist)s" before marking "%(action)s" as done.',
                    checklist=action.checklist_template_id.display_name, action=action.name,
                ))

    # ── Buttons ──────────────────────────────────────────────────────────
    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reopen(self):
        self.write({'state': 'open'})

    def action_open_checklist(self):
        """Open this action's checklist, creating it from the Required
        Checklist the first time."""
        self.ensure_one()
        if not self.checklist_template_id:
            raise UserError(self.env._('This action has no required checklist.'))
        if not self.checklist_id:
            self.checklist_id = self.env['checklist.checklist'].create({
                'template_id': self.checklist_template_id.id,
                'company_id': self.company_id.id,
                'user_id': self.env.user.id,
                'date_due': self.date_deadline and fields.Date.context_today(self, self.date_deadline),
            })
            if self.state == 'open':
                self.state = 'in_progress'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'checklist.checklist',
            'res_id': self.checklist_id.id,
            'view_mode': 'form',
        }

    def action_open_source(self):
        self.ensure_one()
        field_name, record = self._action_source()
        if not record:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'res_id': record.id,
            'view_mode': 'form',
        }

    def action_open_copies(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Copies'),
            'res_model': 'advanced.action',
            'view_mode': 'list,form',
            'domain': [('origin_id', '=', self.id)],
        }

    def action_duplicate_for_users(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Duplicate for Users'),
            'res_model': 'advanced.action.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_origin_id': self.id},
        }

    # ── Checklists ───────────────────────────────────────────────────────
    def _checklists_completed(self, checklists):
        """Completing an action's checklist completes the action."""
        actions = self.sudo().search([
            ('checklist_id', 'in', checklists.ids), ('state', 'in', ('open', 'in_progress')),
        ])
        actions.write({'state': 'done'})

    # ── Notifications ────────────────────────────────────────────────────
    def _notify(self, event, partners_by_action=None):
        """Send this event's Notification Templates (not when Workflow
        Automation is installed: its workflows send them instead)."""
        if not self or self.env.context.get('advanced_action_no_notify'):
            return
        Notification = self.env['advanced.action.notification'].sudo()
        if not Notification._notifications_enabled():
            return
        templates = Notification.search([('event', '=', event)])
        for template in templates:
            for action in self:
                extra = partners_by_action.get(action) if partners_by_action is not None else None
                if partners_by_action is not None and not extra:
                    continue
                template._send(action, assignees=extra)

    @api.model
    def _cron_notify_deadlines(self):
        """Daily: Due Soon and Overdue notifications, once per action."""
        Notification = self.env['advanced.action.notification'].sudo()
        if not Notification._notifications_enabled():
            return
        now = fields.Datetime.now()
        open_states = ('open', 'in_progress')
        overdue = self.sudo().search([
            ('state', 'in', open_states), ('date_deadline', '<', now), ('overdue_notified', '=', False),
        ])
        overdue._notify('overdue')
        overdue.write({'overdue_notified': True})
        for template in Notification.search([('event', '=', 'due_soon')]):
            due_soon = self.sudo().search([
                ('state', 'in', open_states), ('due_soon_notified', '=', False),
                ('date_deadline', '>=', now),
                ('date_deadline', '<=', now + timedelta(days=template.days_before)),
            ])
            for action in due_soon:
                template._send(action)
            due_soon.write({'due_soon_notified': True})

    # ── Moving actions between apps' models ──────────────────────────────
    @api.model
    def _date_to_deadline(self, day, user=None):
        """A Due Date as a Due At: the end of that working day in the user's
        time zone."""
        if not day:
            return False
        tz = pytz.timezone((user or self.env.user).tz or 'UTC')
        local = tz.localize(datetime.combine(day, time(DUE_HOUR)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _deadline_to_date(self, deadline, user=None):
        if not deadline:
            return False
        tz = pytz.timezone((user or self.env.user).tz or 'UTC')
        return pytz.utc.localize(deadline).astimezone(tz).date()

    @api.model
    def _transfer_records(self, records, target_model, vals_func):
        """Copy ``records`` into ``target_model`` with ``vals_func(record)``,
        keeping their author and dates, Organisation, chatter, followers,
        activities and attachments, then delete them. Bridge modules use it
        to move an app's former actions in here on install, and back on
        uninstall. Returns {old id: new id}."""
        Target = self.env[target_model].sudo().with_context(
            tracking_disable=True, mail_create_nolog=True, mail_create_nosubscribe=True, mail_notrack=True,
            advanced_action_no_notify=True,
        )
        records = records.sudo().with_context(active_test=False)
        cr = self.env.cr
        mapping = {}
        for record in records:
            vals = vals_func(record)
            if all(name in record._fields and name in Target._fields for name in ORG_FIELD_NAMES):
                vals.update({name: record[name].id for name in ORG_FIELD_NAMES})
            mapping[record.id] = Target.create(vals).id
        if not mapping:
            return mapping
        source_model = records._name
        source_table = records._table
        is_thread = (
            'message_ids' in records._fields and 'message_ids' in Target._fields
        )
        model_id = self.env['ir.model']._get_id(target_model)
        for old_id, new_id in mapping.items():
            cr.execute(f"""
                UPDATE "{Target._table}" AS t
                   SET create_uid = s.create_uid, create_date = s.create_date,
                       write_uid = s.write_uid, write_date = s.write_date
                  FROM "{source_table}" AS s
                 WHERE s.id = %s AND t.id = %s
            """, (old_id, new_id))
            cr.execute(
                "UPDATE ir_attachment SET res_model = %s, res_id = %s WHERE res_model = %s AND res_id = %s",
                (target_model, new_id, source_model, old_id),
            )
            if is_thread:
                cr.execute(
                    "UPDATE mail_message SET model = %s, res_id = %s WHERE model = %s AND res_id = %s",
                    (target_model, new_id, source_model, old_id),
                )
                cr.execute("""
                    DELETE FROM mail_followers
                     WHERE res_model = %s AND res_id = %s
                       AND partner_id IN (SELECT partner_id FROM mail_followers
                                           WHERE res_model = %s AND res_id = %s)
                """, (target_model, new_id, source_model, old_id))
                cr.execute(
                    "UPDATE mail_followers SET res_model = %s, res_id = %s WHERE res_model = %s AND res_id = %s",
                    (target_model, new_id, source_model, old_id),
                )
                cr.execute("""
                    UPDATE mail_activity SET res_model = %s, res_model_id = %s, res_id = %s
                     WHERE res_model = %s AND res_id = %s
                """, (target_model, model_id, new_id, source_model, old_id))
        self.env.invalidate_all()
        records.unlink()
        return mapping

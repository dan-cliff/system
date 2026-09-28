from datetime import datetime, time

import pytz
from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_datetime


class KennelTask(models.Model):
    """One job on the daily to-do list: a feed, a dose of medication or an observation round."""
    _name = 'kennel.task'
    _description = 'Daily Task'
    _order = 'scheduled_datetime, task_type, resident_id, id'
    _check_company_auto = True

    name = fields.Char(compute='_compute_name', store=True)
    task_type = fields.Selection(
        [('feed', 'Feed'), ('medication', 'Medication'), ('observation', 'Observation')],
        string='Type', required=True, readonly=True, index=True,
    )
    key = fields.Char(readonly=True, copy=False, help='Stops the same task being created twice.')
    booking_id = fields.Many2one('kennel.booking', required=True, readonly=True, ondelete='cascade', index=True)
    line_id = fields.Many2one('kennel.booking.line', string='Stay', required=True, readonly=True, ondelete='cascade')
    medication_id = fields.Many2one('kennel.medication', readonly=True, ondelete='cascade')
    resident_id = fields.Many2one(related='line_id.resident_id', string='Animal', store=True, index=True)
    image_128 = fields.Image(related='resident_id.image_128')
    partner_id = fields.Many2one(related='booking_id.partner_id', string='Customer', store=True)
    yard_id = fields.Many2one(related='line_id.yard_id', string='Yard', store=True)
    company_id = fields.Many2one(related='booking_id.company_id', store=True, index=True)
    date = fields.Date(required=True, readonly=True, index=True, help='Day on the to-do list.')
    scheduled_datetime = fields.Datetime(string='Due', required=True, readonly=True)
    state = fields.Selection(
        [('todo', 'To Do'), ('done', 'Done'), ('cancelled', 'Not Required')],
        default='todo', required=True, readonly=True, index=True,
    )
    overdue = fields.Boolean(compute='_compute_overdue')
    instructions = fields.Text(compute='_compute_instructions')
    medical_notes = fields.Text(related='line_id.medical_notes', string='Medical Care Requirements')

    # Feed
    food = fields.Text(compute='_compute_instructions', string='Food')
    quantity_given = fields.Char(
        string='Food Given', compute='_compute_quantity_given', store=True, readonly=False,
    )
    consumption_id = fields.Many2one('kennel.feed.consumption', string='Food Eaten', check_company=True)
    # Medication
    dose_given = fields.Char(compute='_compute_dose_given', store=True, readonly=False)
    outcome_id = fields.Many2one('kennel.dose.outcome', string='Outcome', check_company=True)
    administration_id = fields.Many2one('kennel.medication.administration', string='Medication Log Entry', readonly=True)
    # Observation
    observation_type_id = fields.Many2one(
        'kennel.observation.type', string='Observation Type', check_company=True,
        default=lambda self: self.env.ref('boarding_kennel_manager.kennel_observation_type_general', raise_if_not_found=False),
    )
    summary = fields.Char(help='One line on how the animal is, e.g. "Bright and playful".')
    concern = fields.Boolean(compute='_compute_concern', store=True, readonly=False,
                             help='Needs follow-up, e.g. a vet visit or letting the owner know.')
    observation_id = fields.Many2one('kennel.observation', readonly=True)

    notes = fields.Text()
    photo_ids = fields.Many2many('ir.attachment', string='Photos',
                                 help='Photos are added to the animal\'s history and shared with the customer.')
    problem = fields.Boolean(compute='_compute_problem', store=True, string='Needs Attention')
    done_by_id = fields.Many2one('res.users', string='Completed By', readonly=True)
    done_datetime = fields.Datetime(string='Completed At', readonly=True)
    message_id = fields.Many2one('mail.message', string='History Entry', readonly=True)

    _key_uniq = models.Constraint('UNIQUE (key)', 'This task is already on the to-do list.')

    @api.depends('task_type', 'resident_id', 'medication_id')
    def _compute_name(self):
        labels = dict(self._fields['task_type']._description_selection(self.env))
        for task in self:
            what = task.medication_id.name if task.task_type == 'medication' else labels.get(task.task_type)
            task.name = f'{what} - {task.resident_id.name}'

    @api.depends('scheduled_datetime', 'state')
    def _compute_overdue(self):
        now = fields.Datetime.now()
        for task in self:
            task.overdue = task.state == 'todo' and task.scheduled_datetime < now

    @api.depends('task_type', 'line_id', 'medication_id', 'scheduled_datetime')
    def _compute_instructions(self):
        for task in self:
            line, medication = task.line_id, task.medication_id
            task.food = False
            if task.task_type == 'feed':
                task.food = line._feed_description(task._local_slot()) or False
                parts = [
                    task.food,
                    self.env._('Owner supplies the food.') if line.owner_supplied_food else '',
                    line.feeding_instructions,
                ]
            elif task.task_type == 'medication':
                parts = [
                    ' - '.join(part for part in (medication.name, medication.dose, medication.route_id.name) if part),
                    medication.times, medication.instructions,
                ]
            else:
                parts = [line.resident_id.behaviour_notes]
            task.instructions = '\n'.join(part for part in parts if part) or False

    @api.depends('line_id.food')
    def _compute_quantity_given(self):
        for task in self:
            task.quantity_given = task.line_id._feed_description(task._local_slot()) or False \
                if task.task_type == 'feed' else False

    def _local_slot(self):
        """(hour, minute) of the task's due time in the kennel's timezone."""
        self.ensure_one()
        if not self.scheduled_datetime:
            return None
        tz = self.booking_id.company_id._kennel_tz() if self.booking_id else pytz.utc
        local = pytz.utc.localize(self.scheduled_datetime).astimezone(tz)
        return local.hour, local.minute

    @api.depends('medication_id.dose')
    def _compute_dose_given(self):
        for task in self:
            task.dose_given = task.medication_id.dose if task.task_type == 'medication' else False

    @api.depends('observation_type_id')
    def _compute_concern(self):
        for task in self:
            task.concern = task.observation_type_id.concern

    @api.depends('task_type', 'consumption_id.problem', 'outcome_id.problem', 'concern')
    def _compute_problem(self):
        for task in self:
            task.problem = {
                'feed': task.consumption_id.problem,
                'medication': task.outcome_id.problem,
                'observation': task.concern,
            }.get(task.task_type, False)

    # ------------------------------------------------------------------
    # Generating the daily list
    # ------------------------------------------------------------------

    @api.model
    def _generate_for_bookings(self, bookings, day=None):
        """Add each checked-in booking's feeds, doses and observation rounds for `day` (default: today
        in the kennel's timezone). Only times during the stay are added, and existing tasks are kept."""
        vals_list = []
        for booking in bookings.filtered(lambda b: b.state == 'checked_in'):
            tz = booking.company_id._kennel_tz()
            booking_day = day or datetime.now(tz).date()
            start = min(filter(None, (booking.arrival_datetime, booking.checked_in_datetime)))
            existing = set(booking.task_ids.mapped('key'))
            obs_times = booking.company_id._kennel_observation_times()

            def add(task_type, line, times, medication=None):
                for hour, minute in times:
                    local = tz.localize(datetime.combine(booking_day, time(hour, minute)))
                    due = local.astimezone(pytz.utc).replace(tzinfo=None)
                    if not start <= due < booking.departure_datetime:
                        continue
                    key = f'{task_type}-{line.id}-{medication.id if medication else 0}-{due:%Y%m%d%H%M}'
                    if key in existing:
                        continue
                    existing.add(key)
                    vals_list.append({
                        'task_type': task_type, 'key': key, 'booking_id': booking.id, 'line_id': line.id,
                        'medication_id': medication.id if medication else False,
                        'date': booking_day, 'scheduled_datetime': due,
                    })

            for line in booking.line_ids:
                add('feed', line, line._feed_times())
                add('observation', line, obs_times)
            for medication in booking.medication_ids:
                if medication.start_date and booking_day < medication.start_date:
                    continue
                if medication.end_date and booking_day > medication.end_date:
                    continue
                line = booking.line_ids.filtered(lambda l: l.resident_id == medication.resident_id)[:1]
                if line:
                    add('medication', line, medication.frequency_id._get_times(), medication)
        return self.create(vals_list)

    @api.model
    def _cron_generate_tasks(self):
        bookings = self.env['kennel.booking'].sudo().search([('state', '=', 'checked_in')])
        self.sudo()._generate_for_bookings(bookings)

    @api.model
    def action_refresh_today(self):
        """Menu/button: make sure today's tasks for every checked-in animal are on the list."""
        bookings = self.env['kennel.booking'].search([('state', '=', 'checked_in')])
        self._generate_for_bookings(bookings)
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    # ------------------------------------------------------------------
    # Closing out
    # ------------------------------------------------------------------

    def _check_complete_values(self):
        self.ensure_one()
        missing = {
            'feed': not self.consumption_id and self.env._('how much of the food was eaten'),
            'medication': not self.outcome_id and self.env._('the outcome of the dose'),
            'observation': not (self.summary or '').strip() and self.env._('a summary of the observation'),
        }.get(self.task_type)
        if missing:
            raise UserError(self.env._('%(task)s: enter %(missing)s first.', task=self.name, missing=missing))

    def action_complete(self):
        for task in self:
            if task.state != 'todo':
                raise UserError(self.env._('%s is already closed.', task.name))
            task._check_complete_values()
            now = fields.Datetime.now()
            if task.task_type == 'medication':
                task.administration_id = self.env['kennel.medication.administration'].create({
                    'booking_id': task.booking_id.id,
                    'medication_id': task.medication_id.id,
                    'administered_datetime': now,
                    'dose_given': task.dose_given,
                    'outcome_id': task.outcome_id.id,
                    'notes': task.notes,
                })
            elif task.task_type == 'observation':
                task.observation_id = self.env['kennel.observation'].create({
                    'booking_id': task.booking_id.id,
                    'resident_id': task.resident_id.id,
                    'observation_datetime': now,
                    'type_id': task.observation_type_id.id,
                    'summary': task.summary,
                    'details': task.notes,
                    'concern': task.concern,
                })
            task.write({'state': 'done', 'done_by_id': self.env.user.id, 'done_datetime': now})
            task._post_to_resident()
        return True

    def action_not_required(self):
        self.filtered(lambda task: task.state == 'todo').write({'state': 'cancelled'})

    def action_reopen(self):
        for task in self:
            if task.administration_id or task.observation_id or task.message_id:
                raise UserError(self.env._(
                    '%s was completed and logged against the animal, so it can\'t be reopened.', task.name))
        self.write({'state': 'todo', 'done_by_id': False, 'done_datetime': False})

    def _history_lines(self):
        """What the keeper recorded, as (label, value) pairs for the animal's history."""
        self.ensure_one()
        rows = {
            'feed': [(self.env._('Given'), self.quantity_given),
                     (self.env._('Eaten'), self.consumption_id.name)],
            'medication': [(self.env._('Dose'), self.dose_given), (self.env._('Outcome'), self.outcome_id.name)],
            'observation': [(self.env._('Type'), self.observation_type_id.name), (self.env._('Summary'), self.summary),
                            (self.env._('Concern'), self.env._('Yes') if self.concern else False)],
        }[self.task_type]
        return [(label, value) for label, value in rows + [(self.env._('Notes'), self.notes)] if value]

    def _post_to_resident(self):
        """Log the completed task on the animal's chatter (shared with the customer), with its photos."""
        self.ensure_one()
        resident = self.resident_id
        when = format_datetime(self.env, self.done_datetime, dt_format='dd/MM/yyyy HH:mm')
        body = Markup('<p><strong>%s</strong> <span class="text-muted">- %s</span></p><ul>%s</ul>') % (
            self.name, when,
            Markup('').join(Markup('<li>%s: %s</li>') % (label, value) for label, value in self._history_lines()),
        )
        photos = self.env['ir.attachment']
        for photo in self.photo_ids.sudo():
            photos |= photo.copy({'res_model': resident._name, 'res_id': resident.id})
        photos.generate_access_token()
        self.message_id = resident.message_post(
            body=body, message_type='comment', subtype_xmlid='boarding_kennel_manager.mt_kennel_care',
            attachment_ids=photos.ids,
        )

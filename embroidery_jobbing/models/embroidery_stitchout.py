# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

STITCHOUT_STATE_SELECTION = [
    ('queued', 'Queued'),
    ('sent', 'Waiting to Start'),
    ('stitching', 'Stitching'),
    ('paused', 'Paused'),
    ('error', 'Error'),
    ('done', 'Done'),
    ('cancelled', 'Cancelled'),
]

EVENT_TYPE_SELECTION = [
    ('queued', 'Queued'),
    ('sent', 'Sent to Machine'),
    ('started', 'Started'),
    ('resumed', 'Resumed'),
    ('paused', 'Paused'),
    ('color_change', 'Colour Change'),
    ('error', 'Error'),
    ('info', 'Info'),
    ('done', 'Completed'),
    ('cancelled', 'Cancelled'),
]

# Seconds of stitching before the measured speed is trusted for the ETA.
MIN_SECONDS_FOR_MEASURED_RATE = 30


def format_duration(seconds):
    seconds = int(round(max(seconds or 0, 0)))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return '%d h %02d min' % (hours, minutes)
    if minutes:
        return '%d min %02d s' % (minutes, seconds)
    return '%d s' % seconds


class EmbroideryStitchout(models.Model):
    """One piece of a job stitched on a machine, with its live progress."""
    _name = 'embroidery.stitchout'
    _description = 'Embroidery Stitch Out'
    _order = 'id desc'

    _OPEN_STATES = ('queued', 'sent', 'stitching', 'paused', 'error')
    _ACTIVE_STATES = ('stitching', 'paused', 'error')

    name = fields.Char(required=True, readonly=True, copy=False, default='/')
    job_id = fields.Many2one('embroidery.job', string='Job', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='job_id.company_id', store=True, index=True)
    partner_id = fields.Many2one(related='job_id.partner_id', string='Customer')
    machine_id = fields.Many2one('embroidery.machine', string='Machine', required=True, ondelete='restrict',
                                 index=True)
    design_id = fields.Many2one('embroidery.design', string='Design', required=True, ondelete='restrict')
    piece_number = fields.Integer(string='Piece', readonly=True)
    state = fields.Selection(STITCHOUT_STATE_SELECTION, string='Status', default='queued', required=True,
                             readonly=True, copy=False, index=True)

    # ── Progress (reported by the bridge, or estimated) ───────────────────
    total_stitches = fields.Integer(readonly=True)
    color_count = fields.Integer(string='Colours', readonly=True)
    current_stitch = fields.Integer(readonly=True)
    current_color = fields.Integer(string='Current Colour No.', readonly=True,
                                   help='1 for the first colour. Reported by the bridge, or worked out from the stitch.')
    speed_spm = fields.Integer(string='Speed (spm)', readonly=True)
    has_live_data = fields.Boolean(string='Live Progress', readonly=True,
                                   help='The machine reports its stitch count. Without it, progress is estimated '
                                        'from the time spent stitching.')
    date_queued = fields.Datetime(string='Queued On', default=fields.Datetime.now, readonly=True)
    date_sent = fields.Datetime(string='Sent On', readonly=True)
    date_started = fields.Datetime(string='Started On', readonly=True)
    date_done = fields.Datetime(string='Finished On', readonly=True)
    date_last_update = fields.Datetime(string='Last Update', readonly=True)
    stitching_since = fields.Datetime(readonly=True)
    stitching_seconds = fields.Float(readonly=True, help='Time spent stitching before the current run.')
    error_message = fields.Char(string='Last Error', readonly=True)
    error_count = fields.Integer(string='Errors', readonly=True)
    event_ids = fields.One2many('embroidery.stitchout.event', 'stitchout_id', string='Events', readonly=True)

    progress = fields.Float(compute='_compute_progress', help='Percentage stitched.')
    elapsed_seconds = fields.Integer(string='Stitching Time', compute='_compute_progress')
    remaining_seconds = fields.Integer(string='Time Remaining', compute='_compute_progress')
    estimated_seconds = fields.Integer(string='Estimated Time', compute='_compute_progress')
    date_eta = fields.Datetime(string='ETA', compute='_compute_progress')
    elapsed_display = fields.Char(string='Time Stitching', compute='_compute_progress')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            job = self.env['embroidery.job'].browse(vals['job_id'])
            design = self.env['embroidery.design'].browse(vals.get('design_id') or job.design_id.id)
            vals.setdefault('design_id', design.id)
            vals.setdefault('total_stitches', design.stitch_count)
            vals.setdefault('color_count', design.color_count)
            vals.setdefault('current_color', 1 if design.color_count else 0)
            # Cancelled stitch outs don't use up a piece, but keep their own name.
            vals['piece_number'] = len(job.stitchout_ids.filtered(lambda s: s.state != 'cancelled')) + 1
            vals['name'] = '%s/%s' % (job.name, len(job.stitchout_ids) + 1)
        stitchouts = super().create(vals_list)
        for stitchout in stitchouts:
            stitchout._log('queued', _('Queued for %s.', stitchout.machine_id.name))
            if stitchout.machine_id.driver == 'manual':
                # Nothing delivers the file: the operator loads it on the machine.
                stitchout._set_state('sent', _('Download the design and load it on the machine.'))
        return stitchouts

    # ── Progress ──────────────────────────────────────────────────────────
    def _active_seconds(self, now=None):
        self.ensure_one()
        now = now or fields.Datetime.now()
        seconds = self.stitching_seconds
        if self.state == 'stitching' and self.stitching_since:
            seconds += (now - self.stitching_since).total_seconds()
        return seconds

    def _estimate_remaining(self, stitch):
        """Seconds to stitch from ``stitch`` to the end at the machine's usual speed."""
        self.ensure_one()
        number, _color = self.design_id._color_at(stitch) if self.design_id.color_ids else (1, None)
        remaining_changes = max((self.color_count or 1) - number, 0)
        return self.machine_id._estimate_seconds(max(self.total_stitches - stitch, 0), remaining_changes)

    @api.depends('state', 'current_stitch', 'total_stitches', 'stitching_seconds', 'stitching_since')
    def _compute_progress(self):
        now = fields.Datetime.now()
        for stitchout in self:
            total = stitchout.total_stitches
            estimated = stitchout.machine_id._estimate_seconds(total, (stitchout.color_count or 1) - 1)
            elapsed = stitchout._active_seconds(now)
            stitchout.estimated_seconds = round(estimated)
            stitchout.elapsed_seconds = round(elapsed)
            stitchout.elapsed_display = format_duration(elapsed)
            if stitchout.state == 'done':
                progress, remaining = 100.0, 0
            elif stitchout.state == 'cancelled' or not total:
                progress, remaining = (stitchout.current_stitch / total * 100.0) if total else 0.0, 0
            elif stitchout.has_live_data:
                stitch = min(stitchout.current_stitch, total)
                progress = stitch / total * 100.0
                if elapsed >= MIN_SECONDS_FOR_MEASURED_RATE and stitch:
                    # The measured rate already includes colour changes and stops.
                    remaining = (total - stitch) / (stitch / elapsed)
                else:
                    remaining = stitchout._estimate_remaining(stitch)
            elif stitchout.state in self._ACTIVE_STATES:
                progress = min(elapsed / estimated * 100.0, 99.0) if estimated else 0.0
                remaining = max(estimated - elapsed, 0)
            else:
                progress, remaining = 0.0, estimated
            stitchout.progress = progress
            stitchout.remaining_seconds = round(remaining)
            stitchout.date_eta = (
                fields.Datetime.add(now, seconds=round(remaining))
                if stitchout.state in self._OPEN_STATES else False
            )

    def _display_stitch(self):
        """The stitch reached: reported, or estimated from the progress."""
        self.ensure_one()
        if self.has_live_data or self.state in ('done', 'cancelled'):
            return min(self.current_stitch, self.total_stitches) if self.state != 'done' else self.total_stitches
        return round(self.total_stitches * self.progress / 100.0)

    # ── State changes ─────────────────────────────────────────────────────
    def _log(self, event_type, message=False, code=False, stitch=None):
        for stitchout in self:
            self.env['embroidery.stitchout.event'].create({
                'stitchout_id': stitchout.id,
                'event_type': event_type,
                'message': message,
                'code': code,
                'stitch': stitchout.current_stitch if stitch is None else stitch,
            })

    def _set_state(self, state, message=False, code=False):
        """Move to ``state``, keeping the stitching time and the event log."""
        now = fields.Datetime.now()
        for stitchout in self:
            old = stitchout.state
            if old in ('done', 'cancelled'):
                continue
            if old == state:
                if state == 'error' and message and message != stitchout.error_message:
                    stitchout._report_error(message, code)
                continue
            vals = {'state': state, 'date_last_update': now}
            if old == 'stitching' and stitchout.stitching_since:
                vals['stitching_seconds'] = stitchout._active_seconds(now)
                vals['stitching_since'] = False
            if state == 'stitching':
                vals['stitching_since'] = now
                vals.setdefault('date_sent', stitchout.date_sent or now)
                if not stitchout.date_started:
                    vals['date_started'] = now
            elif state == 'sent':
                vals['date_sent'] = now
            elif state == 'done':
                vals['date_done'] = now
                vals['current_stitch'] = stitchout.total_stitches
                vals['current_color'] = stitchout.color_count
            elif state == 'cancelled':
                vals['date_done'] = now
            stitchout.write(vals)

            if state == 'error':
                stitchout._report_error(message or _('The machine stopped with an error.'), code)
            elif state == 'stitching':
                stitchout._log('started' if old in ('queued', 'sent') else 'resumed', message)
            elif state == 'done':
                stitchout._log('done', message or _('Stitched in %s.', format_duration(stitchout.elapsed_seconds)))
                stitchout.job_id.message_post(body=_(
                    'Piece %(piece)s finished on %(machine)s in %(time)s.',
                    piece=stitchout.piece_number, machine=stitchout.machine_id.name,
                    time=format_duration(stitchout.elapsed_seconds)))
                stitchout.job_id._check_complete()
            else:
                stitchout._log(state, message, code)

    def _report_error(self, message, code=False):
        self.ensure_one()
        self.write({'error_message': message, 'error_count': self.error_count + 1})
        self._log('error', message, code)
        text = '%s: %s' % (code, message) if code else message
        self.job_id.message_post(body=_(
            '%(machine)s reported an error on piece %(piece)s at stitch %(stitch)s: %(error)s',
            machine=self.machine_id.name, piece=self.piece_number,
            stitch=self.current_stitch, error=text))

    def _apply_report(self, report):
        """Apply a progress report from the bridge.

        ``report`` keys, all optional: ``status`` (a stitch-out state),
        ``stitch``, ``color`` (1 for the first colour), ``speed`` (spm),
        ``message``, ``error_code`` and ``events`` (a list of
        ``{'type', 'message', 'code', 'stitch'}``).
        """
        self.ensure_one()
        if self.state in ('done', 'cancelled'):
            return
        vals = {'date_last_update': fields.Datetime.now()}
        stitch = report.get('stitch')
        if isinstance(stitch, int) and stitch >= 0:
            vals['current_stitch'] = min(stitch, self.total_stitches or stitch)
            vals['has_live_data'] = True
            if not isinstance(report.get('color'), int) and self.design_id.color_ids:
                vals['current_color'] = self.design_id._color_at(vals['current_stitch'])[0]
        color = report.get('color')
        if isinstance(color, int) and color > 0:
            vals['current_color'] = min(color, self.color_count or color)
        speed = report.get('speed')
        if isinstance(speed, int) and speed >= 0:
            vals['speed_spm'] = speed
        old_color = self.current_color
        self.write(vals)
        if 'current_color' in vals and vals['current_color'] != old_color and self.state == 'stitching':
            self._log('color_change', _('Colour %(number)s: %(name)s',
                                        number=self.current_color, name=self._color_name(self.current_color)))
        for event in report.get('events') or []:
            if not isinstance(event, dict):
                continue
            event_type = event.get('type')
            if event_type == 'error':
                self._report_error(str(event.get('message') or _('Error')), event.get('code') or False)
            elif event_type in dict(EVENT_TYPE_SELECTION):
                self._log(event_type, event.get('message') or False, event.get('code') or False,
                          event.get('stitch') if isinstance(event.get('stitch'), int) else None)
        status = report.get('status')
        if status in dict(STITCHOUT_STATE_SELECTION) and status != 'queued':
            self._set_state(status, report.get('message') or False, report.get('error_code') or False)

    def _color_name(self, number):
        self.ensure_one()
        colors = self.design_id.color_ids.sorted('sequence')
        if 0 < number <= len(colors):
            return colors[number - 1].name
        return ''

    def _bridge_job(self):
        """What the bridge needs to deliver this stitch out."""
        self.ensure_one()
        design = self.design_id
        return {
            'stitchout_id': self.id,
            'name': self.name,
            'machine_id': self.machine_id.id,
            'job': self.job_id.name,
            'customer': self.job_id.partner_id.display_name or '',
            'design': design.name,
            'filename': design.design_filename or '%s.pes' % design.name,
            'total_stitches': self.total_stitches,
            'colors': [
                {'name': c.name, 'hex': c.color_hex, 'stitches': c.stitch_count}
                for c in design.color_ids.sorted('sequence')
            ],
            'file_url': '/embroidery/bridge/v1/stitchout/%s/file' % self.id,
        }

    # ── Operator actions ──────────────────────────────────────────────────
    def action_operator_start(self):
        for stitchout in self:
            if stitchout.state == 'queued':
                raise UserError(_('%s has not reached the machine yet.', stitchout.name))
        self._set_state('stitching', _('Started by %s.', self.env.user.name))
        return True

    def action_operator_pause(self):
        self._set_state('paused', _('Paused by %s.', self.env.user.name))
        return True

    def action_operator_done(self):
        self._set_state('done')
        return True

    def action_operator_cancel(self):
        self._set_state('cancelled', _('Cancelled by %s.', self.env.user.name))
        return True

    def action_operator_error(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Report a Problem'),
            'res_model': 'embroidery.stitchout.error.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_stitchout_id': self.id},
        }

    def action_download_design(self):
        self.ensure_one()
        return self.job_id.action_download_design()

    # ── Progress monitor ──────────────────────────────────────────────────
    def embroidery_progress_data(self):
        self.ensure_one()
        return self._progress_data()

    def _progress_data(self, job=None, machine=None):
        """Everything the progress monitor shows, for this stitch out."""
        job = job or self.job_id
        if not self:
            return {
                'empty': True,
                'poll': bool(machine),
                'message': _('Nothing is on this machine.') if machine else _('Not sent to a machine yet.'),
                'qty_done': job.qty_done if job else 0,
                'qty': job.product_qty if job else 0,
            }
        self.ensure_one()
        user_tz_date = lambda value: fields.Datetime.context_timestamp(self, value).strftime('%d/%m/%Y %H:%M:%S')
        stitch = self._display_stitch()
        if self.has_live_data or not self.design_id.color_ids:
            color_number = self.current_color
        else:
            color_number = self.design_id._color_at(stitch)[0]
        colors = self.design_id.color_ids.sorted('sequence')
        color = colors[color_number - 1] if 0 < color_number <= len(colors) else colors.browse()
        next_color = colors[color_number] if 0 < color_number < len(colors) else colors.browse()
        state_labels = dict(self._fields['state']._description_selection(self.env))
        event_labels = dict(self.env['embroidery.stitchout.event']._fields['event_type']._description_selection(self.env))
        return {
            'empty': False,
            'id': self.id,
            'name': self.name,
            'state': self.state,
            'state_label': state_labels[self.state],
            'poll': self.state in self._OPEN_STATES,
            'machine': self.machine_id.name,
            'machine_driver': self.machine_id.driver,
            'job': job.name,
            'piece': self.piece_number,
            'qty': job.product_qty,
            'qty_done': job.qty_done,
            'live': self.has_live_data,
            'progress': round(self.progress, 1),
            'stitch': stitch,
            'total_stitches': self.total_stitches,
            'color_number': color_number,
            'color_count': self.color_count,
            'color_name': color.name or '',
            'color_hex': color.color_hex or '',
            'next_color_name': next_color.name or '',
            'next_color_hex': next_color.color_hex or '',
            'speed': self.speed_spm,
            'elapsed_seconds': self.elapsed_seconds,
            'elapsed': format_duration(self.elapsed_seconds),
            'remaining_seconds': self.remaining_seconds,
            'remaining': format_duration(self.remaining_seconds),
            'estimated': format_duration(self.estimated_seconds),
            'started': user_tz_date(self.date_started) if self.date_started else '',
            'finished': user_tz_date(self.date_done) if self.date_done else '',
            'last_update': user_tz_date(self.date_last_update) if self.date_last_update else '',
            'error_message': self.error_message or '' if self.state == 'error' else '',
            'error_count': self.error_count,
            'events': [
                {
                    'id': event.id,
                    'date': user_tz_date(event.date),
                    'type': event.event_type,
                    'label': event_labels.get(event.event_type, event.event_type),
                    'message': event.message or '',
                    'code': event.code or '',
                    'stitch': event.stitch,
                }
                for event in self.event_ids[:8]
            ],
        }


class EmbroideryStitchoutEvent(models.Model):
    _name = 'embroidery.stitchout.event'
    _description = 'Embroidery Stitch Out Event'
    _order = 'date desc, id desc'

    stitchout_id = fields.Many2one('embroidery.stitchout', required=True, ondelete='cascade', index=True)
    job_id = fields.Many2one(related='stitchout_id.job_id', store=True, index=True)
    machine_id = fields.Many2one(related='stitchout_id.machine_id', store=True)
    company_id = fields.Many2one(related='stitchout_id.company_id', store=True)
    date = fields.Datetime(required=True, default=fields.Datetime.now)
    event_type = fields.Selection(EVENT_TYPE_SELECTION, string='Event', required=True)
    message = fields.Char()
    code = fields.Char(string='Error Code')
    stitch = fields.Integer()
    user_id = fields.Many2one('res.users', string='By', default=lambda self: self._default_user_id())

    def _default_user_id(self):
        # Reports from a Node aren't made by anyone.
        return False if self.env.context.get('iot_node') else self.env.user

"""Bring existing data across when On Site is installed.

On Site replaces Odoo's Attendances app (hr_attendance) and Attendance Kiosks
(attendance_kiosks). When either is installed, its records are copied into On
Site so both can be uninstalled afterwards:

* attendances (hr.attendance), keeping who created them and when;
* kiosks with their sign in rules and questionnaire triggers;
* kiosk questionnaires, questions and choices (On Site's own copies of the two
  starter questionnaires both apps ship are archived in favour of the imported ones);
* questionnaire responses and answers;
* sign in / out alerts, their conditions and history.

Kiosks get new URLs (/onsite/...): set the kiosk devices up again with them.
Chatter messages are not copied.
"""
import logging

from odoo import Command

_logger = logging.getLogger(__name__)

BATCH = 500
# Starter questionnaires both modules ship with the same XML ids.
SHARED_XMLIDS = ['questionnaire_fit_for_work', 'questionnaire_site_induction']


def post_init_hook(env):
    env = env(context=dict(
        env.context, active_test=False, tracking_disable=True, mail_create_nolog=True,
        mail_notrack=True, onsite_no_alerts=True,
    ))
    importer = _Importer(env)
    if 'attendance.kiosk' in env:
        importer.import_questionnaires()
        importer.import_kiosks()
    if 'hr.attendance' in env:
        importer.import_attendances()
    if 'attendance.kiosk' in env:
        importer.import_responses()
        importer.import_alerts()


class _Importer:

    def __init__(self, env):
        self.env = env
        self.maps = {}

    # ── Helpers ────────────────────────────────────────────────────────────
    def _map(self, model, record):
        return self.maps.get(model, {}).get(record.id, False) if record else False

    def _copy_audit(self, new_model, pairs, old_model):
        """Keep create_uid / create_date of the copied records (record rules use create_uid)."""
        if not pairs:
            return
        cr = self.env.cr
        new_table = self.env[new_model]._table
        old_table = self.env[old_model]._table
        for start in range(0, len(pairs), BATCH):
            chunk = pairs[start:start + BATCH]
            cr.execute(f"""
                UPDATE {new_table} AS n
                   SET create_uid = o.create_uid, create_date = o.create_date
                  FROM {old_table} AS o, (SELECT unnest(%s::int[]) AS new_id, unnest(%s::int[]) AS old_id) AS m
                 WHERE n.id = m.new_id AND o.id = m.old_id
            """, ([n for n, _o in chunk], [o for _n, o in chunk]))

    def _create(self, new_model, old_model, olds, values):
        """Create a copy of each of ``olds`` with ``values(old)`` and remember the ids."""
        mapping = self.maps.setdefault(new_model, {})
        pairs = []
        New = self.env[new_model].sudo()
        skipped = 0
        for start in range(0, len(olds), BATCH):
            chunk = olds[start:start + BATCH]
            try:
                with self.env.cr.savepoint():
                    news = New.create([values(old) for old in chunk])
                    news.flush_recordset()
                done = list(zip(chunk, news))
            except Exception:  # noqa: BLE001 - copy the rest, report the ones that failed
                done = []
                for old in chunk:
                    try:
                        with self.env.cr.savepoint():
                            new = New.create(values(old))
                            new.flush_recordset()
                        done.append((old, new))
                    except Exception as error:  # noqa: BLE001
                        skipped += 1
                        _logger.warning('On Site: could not copy %s %s: %s', old_model, old.id, error)
            for old, new in done:
                mapping[old.id] = new.id
                pairs.append((new.id, old.id))
        self._copy_audit(new_model, pairs, old_model)
        _logger.info('On Site: copied %s %s records (%s skipped)', len(pairs), old_model, skipped)

    # ── Questionnaires ─────────────────────────────────────────────────────
    def import_questionnaires(self):
        env = self.env
        Old = env['attendance.kiosk.questionnaire'].sudo()
        New = env['advanced.attendance.kiosk.questionnaire'].sudo()
        qmap = self.maps.setdefault('advanced.attendance.kiosk.questionnaire', {})
        question_map = self.maps.setdefault('advanced.attendance.kiosk.question', {})
        option_map = self.maps.setdefault('advanced.attendance.kiosk.question.option', {})
        for xmlid in SHARED_XMLIDS:
            # Both apps ship this starter questionnaire: keep the copy as it was
            # used (and edited) in Attendance Kiosks, and archive On Site's.
            old = env.ref(f'attendance_kiosks.{xmlid}', raise_if_not_found=False)
            starter = env.ref(f'advanced_attendance.{xmlid}', raise_if_not_found=False)
            if old and starter:
                starter.sudo().active = False
        for old in Old.search([]):
            new = New.create({
                'name': old.name,
                'sequence': old.sequence,
                'active': old.active,
                'company_id': old.company_id.id,
                'introduction': old.introduction,
                'blocked_message': old.blocked_message,
            })
            qmap[old.id] = new.id
            for question in old.question_ids:
                new_question = env['advanced.attendance.kiosk.question'].sudo().create({
                    'questionnaire_id': new.id,
                    'sequence': question.sequence,
                    'name': question.name,
                    'help_text': question.help_text,
                    'question_type': question.question_type,
                    'required': question.required,
                    'blocking_answer': question.blocking_answer,
                    'option_ids': [Command.create({
                        'sequence': option.sequence,
                        'name': option.name,
                        'blocks_sign_in': option.blocks_sign_in,
                    }) for option in question.option_ids],
                })
                question_map[question.id] = new_question.id
                for option, new_option in zip(question.option_ids, new_question.option_ids):
                    option_map[option.id] = new_option.id

    # ── Kiosks ─────────────────────────────────────────────────────────────
    def import_kiosks(self):
        kiosks = self.env['attendance.kiosk'].sudo().search([])
        qmap = self.maps.get('advanced.attendance.kiosk.questionnaire', {})
        self._create('advanced.attendance.kiosk', 'attendance.kiosk', kiosks, lambda k: {
            'name': k.name,
            'sequence': k.sequence,
            'active': k.active,
            'company_id': k.company_id.id,
            'work_location_id': k.work_location_id.id,
            'tz': k.tz,
            'welcome_message': k.welcome_message,
            'offline_enabled': k.offline_enabled,
            'roster_refresh_minutes': k.roster_refresh_minutes,
            'identify_badge': k.identify_badge,
            'identify_name': k.identify_name,
            'require_pin': k.require_pin,
            'restrict_to_company': k.restrict_to_company,
            'employee_domain': k.employee_domain,
            'required_course_ids': [Command.set(k.required_course_ids.ids)],
            'expiry_warning_days': k.expiry_warning_days,
            'auto_sign_out': k.auto_sign_out,
            'auto_sign_out_type': k.auto_sign_out_type,
            'auto_sign_out_hours': k.auto_sign_out_hours,
            'auto_sign_out_time': k.auto_sign_out_time,
            'other_sign_in_action': k.other_sign_in_action,
            'other_sign_out_action': k.other_sign_out_action,
            'rule_ids': [Command.create({
                'sequence': rule.sequence,
                'active': rule.active,
                'name': rule.name,
                'rule_type': rule.rule_type,
                'applies_domain': rule.applies_domain,
                'requirement_domain': rule.requirement_domain,
                'required_course_ids': [Command.set(rule.required_course_ids.ids)],
                'any_course_ids': [Command.set(rule.any_course_ids.ids)],
                'message': rule.message,
            }) for rule in k.with_context(active_test=False).rule_ids],
            'questionnaire_line_ids': [Command.create({
                'sequence': line.sequence,
                'questionnaire_id': qmap[line.questionnaire_id.id],
                'trigger': line.trigger,
                'employee_domain': line.employee_domain,
            }) for line in k.questionnaire_line_ids if line.questionnaire_id.id in qmap],
        })

    # ── Attendances ────────────────────────────────────────────────────────
    def import_attendances(self):
        Old = self.env['hr.attendance'].sudo()
        olds = Old.search([], order='employee_id, check_in')
        has_kiosks = 'in_kiosk_id' in Old._fields
        kiosk_model = 'advanced.attendance.kiosk'
        out_modes = dict(self.env['advanced.attendance']._fields['out_mode'].selection)
        in_modes = dict(self.env['advanced.attendance']._fields['in_mode'].selection)

        def values(old):
            vals = {
                'employee_id': old.employee_id.id,
                'check_in': old.check_in,
                'check_out': old.check_out,
                'in_mode': old.in_mode if old.in_mode in in_modes else 'manual',
                'out_mode': old.out_mode if old.out_mode in out_modes else 'manual',
                'in_latitude': old.in_latitude,
                'in_longitude': old.in_longitude,
                'in_location': old.in_location,
                'in_ip_address': old.in_ip_address,
                'in_browser': old.in_browser,
                'out_latitude': old.out_latitude,
                'out_longitude': old.out_longitude,
                'out_location': old.out_location,
                'out_ip_address': old.out_ip_address,
                'out_browser': old.out_browser,
            }
            if has_kiosks:
                vals.update({
                    'in_kiosk_id': self._map(kiosk_model, old.in_kiosk_id),
                    'out_kiosk_id': self._map(kiosk_model, old.out_kiosk_id),
                    'kiosk_transferred': old.kiosk_transferred,
                    'kiosk_offline_in': old.kiosk_offline_in,
                    'kiosk_offline_out': old.kiosk_offline_out,
                    'kiosk_event_in': old.kiosk_event_in,
                    'kiosk_event_out': old.kiosk_event_out,
                })
            return vals

        self._create('advanced.attendance', 'hr.attendance', olds, values)

    # ── Questionnaire responses ────────────────────────────────────────────
    def import_responses(self):
        responses = self.env['attendance.kiosk.response'].sudo().search([], order='id')
        qmap = self.maps.get('advanced.attendance.kiosk.questionnaire', {})
        responses = responses.filtered(lambda r: r.questionnaire_id.id in qmap
                                       and self._map('advanced.attendance.kiosk', r.kiosk_id))
        self._create('advanced.attendance.kiosk.response', 'attendance.kiosk.response', responses, lambda r: {
            'date': r.date,
            'employee_id': r.employee_id.id,
            'kiosk_id': self._map('advanced.attendance.kiosk', r.kiosk_id),
            'questionnaire_id': qmap[r.questionnaire_id.id],
            'attendance_id': self._map('advanced.attendance', r.attendance_id),
            'blocked': r.blocked,
            'offline': r.offline,
            'line_ids': [Command.create({
                'question_id': self._map('advanced.attendance.kiosk.question', line.question_id),
                'question': line.question,
                'answer': line.answer,
                'option_id': self._map('advanced.attendance.kiosk.question.option', line.option_id),
                'blocks_sign_in': line.blocks_sign_in,
            }) for line in r.line_ids],
        })

    # ── Alerts ─────────────────────────────────────────────────────────────
    def import_alerts(self):
        alerts = self.env['attendance.alert'].sudo().search([])
        self._create('advanced.attendance.alert', 'attendance.alert', alerts, lambda a: {
            'name': a.name,
            'active': a.active,
            'company_id': a.company_id.id,
            'requester_id': a.requester_id.id,
            'all_employees': a.all_employees,
            'employee_ids': [Command.set(a.employee_ids.ids)],
            'condition_ids': [Command.create({
                'sequence': condition.sequence,
                'event': condition.event,
                'location_ids': [Command.set(condition.location_ids.ids)],
            }) for condition in a.condition_ids],
            'recurrence': a.recurrence,
            'date_start': a.date_start,
            'date_end': a.date_end,
            **{day: a[day] for day in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')},
            'time_from': a.time_from,
            'time_to': a.time_to,
            'notify_requester': a.notify_requester,
            'channel_ids': [Command.set(a.channel_ids.ids)],
            'note': a.note,
            'last_triggered': a.last_triggered,
        })
        logs = self.env['attendance.alert.log'].sudo().search([], order='id')
        self._create('advanced.attendance.alert.log', 'attendance.alert.log', logs, lambda log: {
            'alert_id': self._map('advanced.attendance.alert', log.alert_id),
            'date': log.date,
            'employee_id': log.employee_id.id,
            'attendance_id': self._map('advanced.attendance', log.attendance_id),
            'event': log.event,
            'work_location_id': log.work_location_id.id,
        })

from datetime import date, datetime, timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class AttendanceKioskCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.address = cls.env['res.partner'].create({'name': 'Workshop Address'})
        cls.location = cls.env['hr.work.location'].create({
            'name': 'Workshop', 'address_id': cls.address.id, 'company_id': cls.company.id,
        })
        cls.yard = cls.env['hr.work.location'].create({
            'name': 'Yard', 'address_id': cls.address.id, 'company_id': cls.company.id,
        })
        Course = cls.env['lms.course']
        cls.induction = Course.create({'name': 'Site Induction', 'course_type': 'training', 'delivery_mode': 'in_person'})
        cls.forklift = Course.create({'name': 'Forklift Licence', 'course_type': 'licence', 'delivery_mode': 'in_person'})
        cls.first_aid = Course.create({'name': 'First Aid', 'course_type': 'qualification', 'delivery_mode': 'in_person'})
        Employee = cls.env['hr.employee']
        cls.alice = Employee.create({'name': 'Alice Able', 'barcode': 'ALICE01', 'pin': '1234', 'company_id': cls.company.id})
        cls.bob = Employee.create({'name': 'Bob Brown', 'barcode': 'BOB01', 'pin': '5678', 'company_id': cls.company.id})
        cls.kiosk = cls.env['attendance.kiosk'].create({
            'name': 'Front Door', 'company_id': cls.company.id, 'work_location_id': cls.location.id, 'tz': 'UTC',
        })
        cls.kiosk_yard = cls.env['attendance.kiosk'].create({
            'name': 'Yard Gate', 'company_id': cls.company.id, 'work_location_id': cls.yard.id, 'tz': 'UTC',
        })
        cls.fit = cls.env.ref('attendance_kiosks.questionnaire_fit_for_work')

    def grant(self, employee, course, expiry=None):
        record = self.env['lms.employee.record'].create({'employee_id': employee.id, 'course_id': course.id})
        record.write({'state': 'completed', 'completion_date': date.today(), 'expiry_date': expiry})
        return record

    def evaluate(self, employee, kiosk=None):
        return (kiosk or self.kiosk)._kiosk_evaluate(employee)[employee.id]

    def answers(self, questionnaire, value):
        return [{'questionnaire_id': questionnaire.id,
                 'answers': {str(q.id): {'value': value} for q in questionnaire.question_ids}}]

    def safe_answers(self):
        # "No" to unwell / impaired, "Yes" to having PPE.
        unwell, impaired, ppe = self.fit.question_ids.sorted('sequence')
        return [{'questionnaire_id': self.fit.id, 'answers': {
            str(unwell.id): {'value': 'no'}, str(impaired.id): {'value': 'no'}, str(ppe.id): {'value': 'yes'},
        }}]


class TestEligibility(AttendanceKioskCase):

    def test_everyone_in_company_by_default(self):
        self.assertTrue(self.evaluate(self.alice)['ok'])
        other = self.env['res.company'].create({'name': 'Other Co'})
        outsider = self.env['hr.employee'].create({'name': 'Out Sider', 'company_id': other.id})
        result = self.evaluate(outsider)
        self.assertFalse(result['ok'])
        self.kiosk.restrict_to_company = False
        self.assertTrue(self.evaluate(outsider)['ok'])

    def test_employee_filter(self):
        self.kiosk.employee_domain = "[('name', 'ilike', 'alice')]"
        self.assertTrue(self.evaluate(self.alice)['ok'])
        self.assertFalse(self.evaluate(self.bob)['ok'])
        self.assertEqual(self.kiosk._kiosk_eligible_employees(), self.alice)

    def test_minimum_capabilities(self):
        self.kiosk.required_course_ids = self.induction
        result = self.evaluate(self.alice)
        self.assertFalse(result['ok'])
        self.assertIn('Site Induction', result['reasons'][0])
        self.grant(self.alice, self.induction)
        self.assertTrue(self.evaluate(self.alice)['ok'])

    def test_expired_capability_does_not_count(self):
        self.kiosk.required_course_ids = self.induction
        self.grant(self.alice, self.induction, expiry=date.today() - timedelta(days=1))
        self.assertFalse(self.evaluate(self.alice)['ok'])

    def test_expiry_warning_and_until(self):
        self.kiosk.required_course_ids = self.induction
        expiry = date.today() + timedelta(days=5)
        self.grant(self.alice, self.induction, expiry=expiry)
        result = self.evaluate(self.alice)
        self.assertTrue(result['ok'])
        self.assertEqual(result['until'], expiry.isoformat())
        self.assertIn(expiry.strftime('%d/%m/%Y'), result['warnings'][0])

    def test_conditional_rule(self):
        self.env['attendance.kiosk.rule'].create({
            'kiosk_id': self.kiosk.id,
            'name': 'Bob drives forklifts',
            'applies_domain': "[('name', '=', 'Bob Brown')]",
            'required_course_ids': [(6, 0, self.forklift.ids)],
            'any_course_ids': [(6, 0, (self.first_aid | self.induction).ids)],
        })
        self.assertTrue(self.evaluate(self.alice)['ok'], 'The rule does not apply to Alice')
        result = self.evaluate(self.bob)
        self.assertFalse(result['ok'])
        self.assertIn('Forklift Licence', result['reasons'][0])
        self.grant(self.bob, self.forklift)
        self.assertFalse(self.evaluate(self.bob)['ok'], 'Bob still needs one of First Aid / Site Induction')
        self.grant(self.bob, self.first_aid)
        self.assertTrue(self.evaluate(self.bob)['ok'])

    def test_requirement_domain_and_message(self):
        self.env['attendance.kiosk.rule'].create({
            'kiosk_id': self.kiosk.id,
            'name': 'Needs a badge',
            'requirement_domain': "[('barcode', '!=', False)]",
            'message': 'You need a badge.',
        })
        nobadge = self.env['hr.employee'].create({'name': 'No Badge', 'company_id': self.company.id})
        self.assertTrue(self.evaluate(self.alice)['ok'])
        self.assertEqual(self.evaluate(nobadge)['reasons'], ['You need a badge.'])

    def test_deny_rule(self):
        self.env['attendance.kiosk.rule'].create({
            'kiosk_id': self.kiosk.id, 'name': 'Not Bob', 'rule_type': 'deny',
            'applies_domain': "[('id', '=', %d)]" % self.bob.id,
        })
        self.assertTrue(self.evaluate(self.alice)['ok'])
        self.assertFalse(self.evaluate(self.bob)['ok'])


class TestSignInOut(AttendanceKioskCase):

    def test_sign_in_and_out(self):
        now = fields.Datetime.now()
        result = self.kiosk._kiosk_sign_in(self.alice, now, [])
        self.assertEqual(result['status'], 'signed_in')
        attendance = self.env['hr.attendance'].search([('employee_id', '=', self.alice.id)])
        self.assertEqual(attendance.in_kiosk_id, self.kiosk)
        self.assertEqual(attendance.kiosk_work_location_id, self.location)
        self.assertEqual(attendance.in_mode, 'kiosk')
        result = self.kiosk._kiosk_sign_out(self.alice, now + timedelta(hours=1))
        self.assertEqual(result['status'], 'signed_out')
        self.assertEqual(attendance.out_kiosk_id, self.kiosk)

    def test_refused_when_not_eligible(self):
        self.kiosk.required_course_ids = self.induction
        result = self.kiosk._kiosk_sign_in(self.alice, fields.Datetime.now(), [])
        self.assertEqual(result['status'], 'refused')
        self.assertFalse(self.env['hr.attendance'].search_count([('employee_id', '=', self.alice.id)]))

    def test_sign_in_elsewhere_signs_out_here(self):
        now = fields.Datetime.now()
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(hours=2), [])
        result = self.kiosk_yard._kiosk_sign_in(self.alice, now, [])
        self.assertEqual(result['status'], 'signed_in')
        self.assertEqual(result['transferred_from'], 'Front Door')
        first, second = self.env['hr.attendance'].search([('employee_id', '=', self.alice.id)], order='check_in')
        self.assertEqual(first.check_out, now)
        self.assertTrue(first.kiosk_transferred)
        self.assertEqual(second.in_kiosk_id, self.kiosk_yard)

    def test_sign_in_elsewhere_blocked(self):
        self.kiosk.other_sign_in_action = 'block'
        now = fields.Datetime.now()
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(hours=2), [])
        result = self.kiosk_yard._kiosk_sign_in(self.alice, now, [])
        self.assertEqual(result['status'], 'error')
        self.assertIn('Front Door', result['message'])

    def test_sign_out_elsewhere(self):
        now = fields.Datetime.now()
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(hours=2), [])
        self.kiosk.other_sign_out_action = 'block'
        self.assertEqual(self.kiosk_yard._kiosk_sign_out(self.alice, now)['status'], 'error')
        self.kiosk.other_sign_out_action = 'allow'
        self.assertEqual(self.kiosk_yard._kiosk_sign_out(self.alice, now)['status'], 'signed_out')

    def test_auto_sign_out_after_hours(self):
        self.kiosk.write({'auto_sign_out': True, 'auto_sign_out_type': 'duration', 'auto_sign_out_hours': 8})
        check_in = fields.Datetime.now() - timedelta(hours=9)
        self.kiosk._kiosk_sign_in(self.alice, check_in, [])
        self.env['attendance.kiosk']._cron_auto_sign_out()
        attendance = self.env['hr.attendance'].search([('employee_id', '=', self.alice.id)])
        self.assertEqual(attendance.check_out, check_in + timedelta(hours=8))
        self.assertEqual(attendance.out_mode, 'auto_check_out')

    def test_auto_sign_out_time_of_day(self):
        self.kiosk.write({'auto_sign_out': True, 'auto_sign_out_type': 'time', 'auto_sign_out_time': 17.5})
        self.assertEqual(self.kiosk._kiosk_auto_sign_out_due(datetime(2026, 1, 5, 8, 0)), datetime(2026, 1, 5, 17, 30))
        # Signed in after the time: signed out at that time the next day.
        self.assertEqual(self.kiosk._kiosk_auto_sign_out_due(datetime(2026, 1, 5, 19, 0)), datetime(2026, 1, 6, 17, 30))
        self.kiosk.tz = 'Australia/Sydney'  # UTC+11 in January
        self.assertEqual(self.kiosk._kiosk_auto_sign_out_due(datetime(2026, 1, 5, 0, 0)), datetime(2026, 1, 5, 6, 30))

    def test_overdue_auto_sign_out_applied_on_next_sign_in(self):
        self.kiosk.write({'auto_sign_out': True, 'auto_sign_out_type': 'duration', 'auto_sign_out_hours': 4})
        now = fields.Datetime.now()
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(hours=10), [])
        result = self.kiosk_yard._kiosk_sign_in(self.alice, now, [])
        self.assertEqual(result['status'], 'signed_in')
        self.assertFalse(result['transferred_from'])
        first = self.env['hr.attendance'].search([('employee_id', '=', self.alice.id)], order='check_in', limit=1)
        self.assertEqual(first.out_mode, 'auto_check_out')


class TestQuestionnaires(AttendanceKioskCase):

    def add_line(self, trigger, kiosk=None, **vals):
        return self.env['attendance.kiosk.questionnaire.line'].create({
            'kiosk_id': (kiosk or self.kiosk).id, 'questionnaire_id': self.fit.id, 'trigger': trigger, **vals,
        })

    def test_every_sign_in(self):
        self.add_line('always')
        now = fields.Datetime.now()
        result = self.kiosk._kiosk_sign_in(self.alice, now, [])
        self.assertEqual(result['status'], 'questionnaire_required')
        result = self.kiosk._kiosk_sign_in(self.alice, now, self.safe_answers())
        self.assertEqual(result['status'], 'signed_in')
        response = self.env['attendance.kiosk.response'].search([('employee_id', '=', self.alice.id)])
        self.assertEqual(len(response.line_ids), 3)
        self.assertTrue(response.attendance_id)
        self.kiosk._kiosk_sign_out(self.alice, now)
        self.assertEqual(self.kiosk._kiosk_questionnaires_due(self.alice, now), self.fit)

    def test_blocking_answer(self):
        self.add_line('always')
        result = self.kiosk._kiosk_sign_in(self.alice, fields.Datetime.now(), self.answers(self.fit, 'yes'))
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(self.env['hr.attendance'].search_count([('employee_id', '=', self.alice.id)]))
        response = self.env['attendance.kiosk.response'].search([('employee_id', '=', self.alice.id)])
        self.assertTrue(response.blocked)

    def test_first_of_day(self):
        self.add_line('first_of_day')
        now = fields.Datetime.now()
        self.assertEqual(self.kiosk._kiosk_questionnaires_due(self.alice, now), self.fit)
        # Signed in at another kiosk earlier today: not the first sign in of the day.
        self.kiosk_yard._kiosk_sign_in(self.alice, now - timedelta(minutes=30), [])
        self.assertFalse(self.kiosk._kiosk_questionnaires_due(self.alice, now))

    def test_first_of_day_at_location(self):
        self.add_line('first_of_day_location')
        now = fields.Datetime.now()
        self.kiosk_yard._kiosk_sign_in(self.alice, now - timedelta(minutes=30), [])
        self.assertEqual(self.kiosk._kiosk_questionnaires_due(self.alice, now), self.fit)
        self.kiosk._kiosk_sign_in(self.alice, now - timedelta(minutes=10), self.safe_answers())
        self.assertFalse(self.kiosk._kiosk_questionnaires_due(self.alice, now))

    def test_first_at_location(self):
        self.add_line('first_at_location')
        now = fields.Datetime.now()
        self.env['hr.attendance'].create({
            'employee_id': self.alice.id, 'check_in': now - timedelta(days=30),
            'check_out': now - timedelta(days=30) + timedelta(hours=8), 'in_kiosk_id': self.kiosk.id,
        })
        self.assertFalse(self.kiosk._kiosk_questionnaires_due(self.alice, now))
        self.assertEqual(self.kiosk._kiosk_questionnaires_due(self.bob, now), self.fit)

    def test_line_filter(self):
        self.add_line('always', employee_domain="[('id', '=', %d)]" % self.bob.id)
        now = fields.Datetime.now()
        self.assertFalse(self.kiosk._kiosk_questionnaires_due(self.alice, now))
        self.assertEqual(self.kiosk._kiosk_questionnaires_due(self.bob, now), self.fit)


class TestOffline(AttendanceKioskCase):

    def test_offline_event_applied_once(self):
        when = fields.Datetime.now() - timedelta(hours=1)
        first = self.kiosk._kiosk_sign_in(self.alice, when, [], offline=True, event='ev-1')
        again = self.kiosk._kiosk_sign_in(self.alice, when, [], offline=True, event='ev-1')
        self.assertEqual(first['status'], 'signed_in')
        self.assertTrue(again.get('duplicate'))
        self.assertEqual(self.env['hr.attendance'].search_count([('employee_id', '=', self.alice.id)]), 1)

    def test_offline_sign_out_corrects_auto_sign_out(self):
        self.kiosk.write({'auto_sign_out': True, 'auto_sign_out_type': 'duration', 'auto_sign_out_hours': 1})
        check_in = fields.Datetime.now() - timedelta(hours=3)
        self.kiosk._kiosk_sign_in(self.alice, check_in, [])
        self.env['attendance.kiosk']._cron_auto_sign_out()
        left = check_in + timedelta(hours=2)
        result = self.kiosk._kiosk_sign_out(self.alice, left, offline=True, event='ev-2')
        self.assertEqual(result['status'], 'signed_out')
        attendance = self.env['hr.attendance'].search([('employee_id', '=', self.alice.id)])
        self.assertEqual(attendance.check_out, left)
        self.assertEqual(attendance.out_mode, 'kiosk')
        self.assertTrue(attendance.kiosk_offline_out)

    def test_offline_answers_recorded(self):
        when = fields.Datetime.now() - timedelta(hours=1)
        result = self.kiosk._kiosk_sign_in(self.alice, when, self.answers(self.fit, 'yes'), offline=True, event='ev-3')
        self.assertEqual(result['status'], 'blocked')
        response = self.env['attendance.kiosk.response'].search([('employee_id', '=', self.alice.id)])
        self.assertTrue(response.blocked)
        self.assertTrue(response.offline)

    def test_roster_payload(self):
        payload = {p['id']: p for p in self.kiosk._kiosk_employee_payloads(self.alice | self.bob)}
        self.assertEqual(payload[self.alice.id]['badge'], self.kiosk._kiosk_hash('ALICE01'))
        self.assertEqual(payload[self.alice.id]['pin'], self.kiosk._kiosk_hash('1234'))
        self.assertIsNone(payload[self.alice.id]['open'])
        self.kiosk._kiosk_sign_in(self.alice, fields.Datetime.now(), [])
        payload = self.kiosk_yard._kiosk_employee_payloads(self.alice)[0]
        self.assertEqual(payload['open']['kiosk_name'], 'Front Door')

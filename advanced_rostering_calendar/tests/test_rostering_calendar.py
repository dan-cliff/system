# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestRosteringCalendar(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.worker = new_test_user(cls.env, 'rcal_worker', name='Wren Worker',
                                   groups='advanced_rostering.group_roster_own')
        cls.colleague = new_test_user(cls.env, 'rcal_colleague', name='Cole Colleague',
                                      groups='advanced_rostering.group_roster_own')
        cls.approver = new_test_user(cls.env, 'rcal_approver', name='Ava Approver',
                                     groups='advanced_rostering.group_leave_approve')
        cls.leave_type = cls.env['rostering.leave.type'].create({'name': 'Annual'})
        cls.group_partner = cls.env.ref('advanced_rostering_calendar.partner_leave_requests_calendar')

    def _leave(self, user=None, **vals):
        user = user or self.worker
        values = {'leave_type_id': self.leave_type.id, 'date_from': date(2026, 12, 7),
                  'date_to': date(2026, 12, 9)}
        values.update(vals)
        return self.env['rostering.leave'].with_user(user).create(values)

    def test_event_follows_leave(self):
        leave = self._leave()
        event = leave.sudo().calendar_event_id
        self.assertTrue(event)
        self.assertTrue(event.allday)
        self.assertEqual((event.start_date, event.stop_date), (date(2026, 12, 7), date(2026, 12, 9)))
        self.assertIn(self.worker.partner_id, event.partner_ids)
        self.assertIn(self.group_partner, event.partner_ids)
        self.assertIn('Draft', event.name)
        leave.with_user(self.worker).action_submit()
        self.assertIn('To Approve', event.name)
        leave.with_user(self.approver).action_approve()
        self.assertIn('Approved', event.name)
        # Changing the event in Calendar is refused: the leave request leads.
        with self.assertRaises(UserError):
            event.with_user(self.worker).write({'name': 'Holiday'})
        leave.with_user(self.approver).action_cancel()
        self.assertFalse(event.exists())
        self.assertFalse(leave.sudo().calendar_event_id)

    def test_event_removed_with_leave(self):
        leave = self._leave()
        event = leave.sudo().calendar_event_id
        leave.unlink()
        self.assertFalse(event.exists())

    def test_visibility(self):
        leave = self._leave()
        event = leave.sudo().calendar_event_id
        Event = self.env['calendar.event']
        self.assertIn(event, Event.with_user(self.worker).search([('res_model', '=', 'rostering.leave')]))
        self.assertIn(event, Event.with_user(self.approver).search([('res_model', '=', 'rostering.leave')]))
        # A colleague cannot see the request in Rostering, so not in Calendar either.
        self.assertNotIn(event, Event.with_user(self.colleague).search([]))

    def test_leave_calendar_offered_once(self):
        Filters = self.env['calendar.filters'].with_user(self.colleague)
        Filters.search_read([('user_id', '=', self.colleague.id)], ['partner_id'])
        mine = self.env['calendar.filters'].search([('user_id', '=', self.colleague.id),
                                                    ('partner_id', '=', self.group_partner.id)])
        self.assertTrue(mine)
        mine.unlink()
        Filters.search_read([('user_id', '=', self.colleague.id)], ['partner_id'])
        self.assertFalse(self.env['calendar.filters'].search([('user_id', '=', self.colleague.id),
                                                              ('partner_id', '=', self.group_partner.id)]))

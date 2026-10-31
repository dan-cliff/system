# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Resync every leave event (no Organisation units, no Meeting activity)
    and log what Calendar holds, to check the shared Leave Requests calendar.

    An end- script: it runs once every module is loaded, so Rostering -
    Personnel's employee fields and record rules are there for the resync
    and the visibility check."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Calendar added a "Meeting" activity to each leave request: remove them.
    activities = env['mail.activity'].search([
        ('res_model', '=', 'rostering.leave'), ('calendar_event_id', '!=', False),
    ])
    activities.unlink()
    leaves = env['rostering.leave'].search([])
    leaves._sync_calendar_event()
    shown = leaves.filtered(lambda l: l.state in ('draft', 'submitted', 'approved'))
    events = env['calendar.event'].search([('res_model', '=', 'rostering.leave')])
    group = env.ref('advanced_rostering_calendar.partner_leave_requests_calendar')
    on_group = events.filtered(lambda e: group in e.partner_ids)
    filters = env['calendar.filters'].search_count([('partner_id', '=', group.id)])
    _logger.info(
        'Rostering - Calendar: %s leave requests (%s to show), %s leave events (%s on the Leave Requests '
        'calendar, partner %s), %s users with the Leave Requests calendar, %s Meeting activities removed.',
        len(leaves), len(shown), len(events), len(on_group), group.id, filters, len(activities),
    )
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    if admin:
        visible = env['calendar.event'].with_user(admin).search([('res_model', '=', 'rostering.leave')])
        _logger.info('Rostering - Calendar: %s leave events visible to %s.', len(visible), admin.login)

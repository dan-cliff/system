# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Put the existing leave requests in Calendar."""
    env['rostering.leave'].with_context(active_test=False).search([])._sync_calendar_event()


def uninstall_hook(env):
    """Take the leave events out of Calendar."""
    events = env['calendar.event'].with_context(active_test=False).search([('res_model', '=', 'rostering.leave')])
    events.with_context(rostering_calendar_sync=True).unlink()

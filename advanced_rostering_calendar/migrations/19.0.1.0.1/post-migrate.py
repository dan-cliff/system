# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Give the existing leave events their request's Organisation."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['rostering.leave'].with_context(active_test=False).search([])._sync_calendar_event()

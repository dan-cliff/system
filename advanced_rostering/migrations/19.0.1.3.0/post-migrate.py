# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Rostering - Calendar installs itself only when Rostering or Calendar is
    installed after it: on databases that already had both, install it now
    (the upgrade picks up modules marked for install while it runs)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Module = env['ir.module.module']
    if not Module.search_count([('name', '=', 'calendar'), ('state', 'in', ('installed', 'to upgrade'))]):
        return
    bridge = Module.search([('name', '=', 'advanced_rostering_calendar'), ('state', '=', 'uninstalled')])
    if bridge:
        bridge.button_install()

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Links made before link types existed become End to Start links.
    env['advanced.project.task']._sync_all_links()

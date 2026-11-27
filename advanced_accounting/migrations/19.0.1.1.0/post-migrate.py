"""Subscriptions: finish taking over the Subscription management app (see hooks.py)."""
from odoo import SUPERUSER_ID, api
from odoo.addons.advanced_accounting.hooks import finish_subscription_takeover


def migrate(cr, version):
    finish_subscription_takeover(api.Environment(cr, SUPERUSER_ID, {}))

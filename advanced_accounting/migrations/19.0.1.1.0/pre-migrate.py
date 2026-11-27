"""Subscriptions: take over the Subscription management app (see hooks.py)."""
from odoo.addons.advanced_accounting.hooks import pre_migrate_subscriptions


def migrate(cr, version):
    pre_migrate_subscriptions(cr)

# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    property_reminder_days = fields.Integer(
        string='Property Reminder Days', default=90,
        help='How many days ahead Property schedules reminders for lease expiries, options to renew, '
             'rent reviews and contract end dates.',
    )

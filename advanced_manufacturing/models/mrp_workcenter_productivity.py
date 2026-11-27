# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MrpWorkcenterProductivity(models.Model):
    _inherit = 'mrp.workcenter.productivity'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', index='btree_not_null', ondelete='set null',
        help='The worker who signed in to the Work Centre app for this time.',
    )

    @api.constrains('workorder_id')
    def _check_open_time_ids(self):
        # Replaces Odoo's check (one open timer per user and work order): workers
        # signed in to the Work Centre app each run their own timer and need not
        # have a user, so timers count per employee when they have one.
        for workorder in self.workorder_id:
            seen = set()
            for time in workorder.time_ids.filtered(lambda t: not t.date_end):
                key = ('employee', time.employee_id.id) if time.employee_id else ('user', time.user_id.id)
                if key in seen:
                    raise ValidationError(_('The Workorder (%s) cannot be started twice!', workorder.display_name))
                seen.add(key)

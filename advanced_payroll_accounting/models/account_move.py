# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    payroll_run_id = fields.Many2one('payroll.run', string='Pay Run', index='btree_not_null', readonly=True,
                                     copy=False)

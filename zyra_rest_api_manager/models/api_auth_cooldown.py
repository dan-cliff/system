# -*- coding: utf-8 -*-

from odoo import fields, models


class ApiAuthCooldownLog(models.Model):
    _name = "api.auth.cooldown.log"
    _description = "API Auth Cooldown Log"
    _rec_name = "cooldown_key"

    cooldown_key = fields.Char(required=True, index=True)
    endpoint = fields.Selection(
        [
            ("login", "Login"),
            ("reset_password", "Reset Password"),
        ],
        required=True,
        index=True,
    )
    identifier = fields.Char(index=True)
    ip_address = fields.Char(index=True)
    failed_count = fields.Integer(default=0, required=True)
    window_start = fields.Datetime()
    blocked_until = fields.Datetime()

    _constraint_cooldown_key_unique = models.Constraint(
        "unique(cooldown_key)", "Cooldown key must be unique."
    )

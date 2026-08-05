# -*- coding: utf-8 -*-

from odoo import fields, models


class ApiRateLimitLog(models.Model):
    _name = "api.rate.limit.log"
    _description = "API Rate Limit Log"
    _rec_name = "identifier"

    endpoint_model = fields.Char(required=True)
    endpoint_record_id = fields.Integer(required=True)
    identifier = fields.Char(required=True)
    window_start = fields.Datetime(required=True)
    count = fields.Integer(default=0, required=True)

    _constraint_rate_limit_unique = models.Constraint(
        "unique(endpoint_model, endpoint_record_id, identifier, window_start)",
        "Rate limit window must be unique per endpoint and identifier.",
    )

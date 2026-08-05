# -*- coding: utf-8 -*-

import secrets

from odoo import api, fields, models


class ApiAppKey(models.Model):
    _name = "api.app.key"
    _description = "API App Key"

    name = fields.Char(required=True)
    key = fields.Char(readonly=True, copy=False)
    active = fields.Boolean(default=True)
    note = fields.Text()

    def action_generate_key(self):
        for record in self:
            record.key = secrets.token_urlsafe(32)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if not record.key:
                record.key = secrets.token_urlsafe(32)
        return records

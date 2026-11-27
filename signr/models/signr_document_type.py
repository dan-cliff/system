# -*- coding: utf-8 -*-
from odoo import fields, models


class SignrDocumentType(models.Model):
    _name = 'signr.document.type'
    _description = "Sign'r Document Type"
    _order = 'sequence, name'

    name = fields.Char('Document Type', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text('Description')

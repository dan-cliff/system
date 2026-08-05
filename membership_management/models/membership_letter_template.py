# -*- coding: utf-8 -*-
from odoo import fields, models


class MembershipLetterTemplate(models.Model):
    _name = 'membership.letter.template'
    _description = 'Membership Letter Template'
    _order = 'name'

    name = fields.Char(string='Template Name', required=True)
    document = fields.Binary(
        string='Template Document (.docx)',
        attachment=True,
    )
    document_filename = fields.Char(string='Document Filename')
    description = fields.Text(string='Description')

# -*- coding: utf-8 -*-
from odoo import api, fields, models

# The answer widget an inspection shows depends on the type, so this stays a
# fixed technical selection rather than an editable option list.
QUESTION_TYPES = [
    ('text', 'Text'),
    ('text_area', 'Text Area'),
    ('number', 'Number'),
    ('integer', 'Integer'),
    ('date', 'Date'),
    ('datetime', 'Datetime'),
    ('buttons', 'Buttons'),
]


class EsmFakTemplate(models.Model):
    _name = 'esm.fak.template'
    _description = 'First Aid Kit Inspection Template'
    _order = 'sequence, name'

    name = fields.Char(string='Template Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(string='Description')
    question_ids = fields.One2many(
        'esm.fak.question', 'template_id', string='Questions', copy=True,
    )
    question_count = fields.Integer(compute='_compute_question_count', string='# Questions')

    @api.depends('question_ids')
    def _compute_question_count(self):
        for template in self:
            template.question_count = len(template.question_ids)


class EsmFakQuestion(models.Model):
    _name = 'esm.fak.question'
    _description = 'First Aid Kit Inspection Question'
    _order = 'template_id, sequence, id'

    template_id = fields.Many2one(
        'esm.fak.template', string='Template', required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    name = fields.Char(string='Question Title', required=True, translate=True)
    description = fields.Text(string='Description', translate=True)
    question_type = fields.Selection(
        QUESTION_TYPES, string='Type', required=True, default='buttons',
    )
    option_ids = fields.One2many(
        'esm.fak.question.option', 'question_id', string='Button Values', copy=True,
        help='The buttons the inspector chooses from when the type is Buttons.',
    )

    def _inspection_line_vals(self):
        self.ensure_one()
        return {
            'question_id': self.id,
            'sequence': self.sequence,
            'name': self.name,
            'description': self.description,
            'question_type': self.question_type,
        }


class EsmFakQuestionOption(models.Model):
    _name = 'esm.fak.question.option'
    _description = 'First Aid Kit Inspection Button Value'
    _order = 'question_id, sequence, id'

    question_id = fields.Many2one(
        'esm.fak.question', string='Question', required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    name = fields.Char(string='Value', required=True, translate=True)
    color = fields.Char(
        string='Colour',
        help='Colour of this button on inspections. Leave empty for a plain button.',
    )

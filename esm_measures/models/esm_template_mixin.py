# -*- coding: utf-8 -*-
import json

from odoo import api, models
from odoo.exceptions import UserError

TEMPLATE_JSON_FORMAT = 'esm_measures.inspection_template'
TEMPLATE_JSON_VERSION = 1


class EsmTemplateMixin(models.AbstractModel):
    """JSON export/import for inspection templates.

    A template model inherits this and has `question_ids` (questions with
    name, description, question_type, sequence and `option_ids`, the Buttons
    values with name, sequence and color).
    """
    _name = 'esm.template.mixin'
    _description = 'ESM Inspection Template Export/Import'

    def action_export_json(self):
        return {
            'type': 'ir.actions.act_url',
            'url': f'/esm_measures/templates/export?model={self._name}&ids={",".join(map(str, self.ids))}',
            'target': 'download',
        }

    def _export_json(self):
        return json.dumps({
            'format': TEMPLATE_JSON_FORMAT,
            'version': TEMPLATE_JSON_VERSION,
            'model': self._name,
            'templates': [template._export_template_vals() for template in self],
        }, indent=2, ensure_ascii=False)

    def _export_template_vals(self):
        self.ensure_one()
        return {
            'name': self.name,
            'description': self.description or '',
            'sequence': self.sequence,
            'questions': [{
                'name': question.name,
                'description': question.description or '',
                'question_type': question.question_type,
                'sequence': question.sequence,
                'options': [{
                    'name': option.name,
                    'sequence': option.sequence,
                    'color': option.color or '',
                } for option in question.option_ids],
            } for question in self.question_ids],
        }

    @api.model
    def _import_json(self, content):
        """Create the templates in a JSON export; returns the new templates."""
        try:
            data = json.loads(content)
        except ValueError as error:
            raise UserError(self.env._('This file is not valid JSON: %s', error)) from error
        if not isinstance(data, dict) or data.get('format') != TEMPLATE_JSON_FORMAT:
            raise UserError(self.env._('This file is not an ESM Measures template export.'))
        if data.get('model') != self._name:
            file_type = self.env['ir.model']._get(data.get('model')).name or data.get('model')
            raise UserError(self.env._(
                'This file holds %(file_type)s records, not %(here)s records: import it from the matching templates list.',
                file_type=file_type, here=self._description,
            ))
        valid_types = dict(self.env[self._fields['question_ids'].comodel_name]._fields['question_type'].selection)
        vals_list = []
        for template in data.get('templates') or []:
            questions = []
            for question in template.get('questions') or []:
                if question.get('question_type') not in valid_types:
                    raise UserError(self.env._(
                        'Question "%(question)s" has an unknown type: %(type)s',
                        question=question.get('name'), type=question.get('question_type'),
                    ))
                questions.append((0, 0, {
                    'name': question['name'],
                    'description': question.get('description') or False,
                    'question_type': question['question_type'],
                    'sequence': question.get('sequence', 10),
                    'option_ids': [(0, 0, {
                        'name': option['name'],
                        'sequence': option.get('sequence', 10),
                        'color': option.get('color') or False,
                    }) for option in question.get('options') or []],
                }))
            vals_list.append({
                'name': template['name'],
                'description': template.get('description') or False,
                'sequence': template.get('sequence', 10),
                'question_ids': questions,
            })
        if not vals_list:
            raise UserError(self.env._('This file holds no templates.'))
        return self.create(vals_list)

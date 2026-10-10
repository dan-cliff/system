# -*- coding: utf-8 -*-
import io
import json
import re
import uuid
import zipfile

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

# The answer widget a checklist shows depends on the type, so this stays a
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

TEMPLATE_JSON_FORMAT = 'checklists.template'
TEMPLATE_JSON_VERSION = 1
# ESM Measures template exports have the same layout (without GUIDs).
IMPORTABLE_JSON_FORMATS = (TEMPLATE_JSON_FORMAT, 'esm_measures.inspection_template')


def _new_uuid(_model=None):
    return str(uuid.uuid4())


class ChecklistTemplate(models.Model):
    _name = 'checklist.template'
    _description = 'Checklist Template'
    _order = 'sequence, name'

    name = fields.Char(string='Template Name', required=True, translate=True)
    # Hidden GUID: JSON imports update the template with the same GUID.
    uuid = fields.Char(string='GUID', required=True, copy=False, readonly=True, default=_new_uuid)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(string='Description')
    group_ids = fields.Many2many(
        'checklist.group', 'checklist_template_group_rel', 'template_id', 'group_id',
        string='Checklist Groups',
    )
    question_ids = fields.One2many(
        'checklist.question', 'template_id', string='Questions', copy=True,
    )
    question_count = fields.Integer(compute='_compute_question_count', string='# Questions')

    _uuid_uniq = models.Constraint('UNIQUE (uuid)', 'Another template already has this GUID.')

    @api.depends('question_ids')
    def _compute_question_count(self):
        for template in self:
            template.question_count = len(template.question_ids)

    # ── Side panel ───────────────────────────────────────────────────────

    @api.model
    def search_panel_select_range(self, field_name, **kwargs):
        # Odoo only builds a single-choice side panel for many2one and
        # selection fields; Checklist Groups is a many2many, so its values
        # and counters are built here (a template counts under each group).
        if field_name != 'group_ids':
            return super().search_panel_select_range(field_name, **kwargs)
        domain = Domain.AND([
            Domain(kwargs.get('search_domain') or []),
            Domain(kwargs.get('category_domain') or []),
            Domain(kwargs.get('filter_domain') or []),
        ])
        counts = {group.id: count for group, count in self._read_group(domain, ['group_ids'], ['__count']) if group}
        groups = self.env['checklist.group'].search_read(
            kwargs.get('comodel_domain') or [], ['display_name'], limit=kwargs.get('limit'),
        )
        values = []
        for group in groups:
            if not kwargs.get('expand') and not counts.get(group['id']):
                continue
            value = {'id': group['id'], 'display_name': group['display_name']}
            if kwargs.get('enable_counters'):
                value['__count'] = counts.get(group['id'], 0)
            values.append(value)
        return {'parent_field': False, 'values': values}

    # ── JSON export ──────────────────────────────────────────────────────

    def action_export_json(self):
        """Download the templates: one as .json, several as a .zip of them."""
        if not self:
            raise UserError(self.env._('Select the templates to export.'))
        return {
            'type': 'ir.actions.act_url',
            'url': f'/checklists/templates/export?ids={",".join(map(str, self.ids))}',
            'target': 'download',
        }

    def action_import_json(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Import JSON into %s', self.name),
            'res_model': 'checklist.template.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_template_id': self.id},
        }

    def _export_json(self):
        return json.dumps({
            'format': TEMPLATE_JSON_FORMAT,
            'version': TEMPLATE_JSON_VERSION,
            'templates': [template._export_template_vals() for template in self],
        }, indent=2, ensure_ascii=False)

    def _export_filename(self):
        self.ensure_one()
        return (re.sub(r'[\\/:*?"<>|]+', '-', self.name).strip() or 'Template') + '.json'

    def _export_zip(self):
        """A .zip holding one JSON file per template."""
        buffer = io.BytesIO()
        used = set()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for template in self:
                filename = template._export_filename()
                stem, number = filename[:-5], 2
                while filename.lower() in used:
                    filename = f'{stem} ({number}).json'
                    number += 1
                used.add(filename.lower())
                archive.writestr(filename, template._export_json())
        return buffer.getvalue()

    def _export_template_vals(self):
        self.ensure_one()
        # Archived questions and values go too, so an import can archive them.
        questions = self.with_context(active_test=False).question_ids
        return {
            'uuid': self.uuid,
            'name': self.name,
            'description': self.description or '',
            'sequence': self.sequence,
            'groups': self.group_ids.mapped('name'),
            'questions': [{
                'uuid': question.uuid,
                'name': question.name,
                'description': question.description or '',
                'question_type': question.question_type,
                'sequence': question.sequence,
                'active': question.active,
                'options': [{
                    'uuid': option.uuid,
                    'name': option.name,
                    'sequence': option.sequence,
                    'color': option.color or '',
                    'active': option.active,
                } for option in question.option_ids],
            } for question in questions],
        }

    # ── JSON import ──────────────────────────────────────────────────────

    @api.model
    def _read_import_file(self, content):
        """The template dicts in a JSON export, or in every JSON file of a .zip."""
        if zipfile.is_zipfile(io.BytesIO(content)):
            templates = []
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                for name in sorted(archive.namelist()):
                    if name.lower().endswith('.json') and not name.startswith('__MACOSX/'):
                        templates += self._read_import_json(archive.read(name), name)
            if not templates:
                raise UserError(self.env._('This .zip file holds no template JSON files.'))
            return templates
        return self._read_import_json(content)

    @api.model
    def _read_import_json(self, content, filename=None):
        try:
            data = json.loads(content)
        except ValueError as error:
            if filename:
                raise UserError(self.env._('%(file)s is not valid JSON: %(error)s', file=filename, error=error)) from error
            raise UserError(self.env._('This file is not valid JSON: %s', error)) from error
        if not isinstance(data, dict) or data.get('format') not in IMPORTABLE_JSON_FORMATS:
            if filename:
                raise UserError(self.env._('%s is not a Checklists template export.', filename))
            raise UserError(self.env._('This file is not a Checklists template export.'))
        templates = data.get('templates') or []
        valid_types = dict(QUESTION_TYPES)
        for template in templates:
            if not template.get('name'):
                raise UserError(self.env._('A template in this file has no name.'))
            for question in template.get('questions') or []:
                if not question.get('name'):
                    raise UserError(self.env._('Template "%s" has a question with no title.', template['name']))
                if question.get('question_type') not in valid_types:
                    raise UserError(self.env._(
                        'Question "%(question)s" has an unknown type: %(type)s',
                        question=question.get('name'), type=question.get('question_type'),
                    ))
                for option in question.get('options') or []:
                    if not option.get('name'):
                        raise UserError(self.env._(
                            'Question "%s" has a button value with no name.', question['name']))
        return templates

    @api.model
    def _import_file(self, content):
        """Import a JSON export or .zip of them: a template whose GUID already
        exists is updated, any other is created. Returns the templates."""
        templates_data = self._read_import_file(content)
        if not templates_data:
            raise UserError(self.env._('This file holds no templates.'))
        Templates = self.with_context(active_test=False)
        templates = self.browse()
        for data in templates_data:
            vals = {
                'name': data['name'],
                'description': data.get('description') or False,
                'sequence': data.get('sequence', 10),
                'group_ids': [fields.Command.set(self._import_group_ids(data.get('groups') or []))],
            }
            template = data.get('uuid') and Templates.search([('uuid', '=', data['uuid'])], limit=1)
            if template:
                template.write(vals)
            else:
                if data.get('uuid'):
                    vals['uuid'] = data['uuid']
                template = self.create(vals)
            template._import_questions(data.get('questions') or [])
            templates |= template
        return templates

    def _import_into(self, content):
        """Import a file's questions into this template (bulk update): a
        question whose GUID is already on this template is updated, any other
        is added. Questions not in the file are left as they are."""
        self.ensure_one()
        templates_data = self._read_import_file(content)
        if len(templates_data) != 1:
            raise UserError(self.env._(
                'This file holds %s templates: import into a template needs a file with exactly one.',
                len(templates_data),
            ))
        self._import_questions(templates_data[0].get('questions') or [])

    @api.model
    def _import_group_ids(self, names):
        Groups = self.env['checklist.group'].with_context(active_test=False)
        ids = []
        for name in names:
            group = Groups.search([('name', '=', name)], limit=1) or Groups.create({'name': name})
            ids.append(group.id)
        return ids

    def _import_questions(self, questions_data):
        self.ensure_one()
        Questions = self.env['checklist.question'].with_context(active_test=False)
        for data in questions_data:
            vals = {
                'name': data['name'],
                'description': data.get('description') or False,
                'question_type': data['question_type'],
                'sequence': data.get('sequence', 10),
                'active': data.get('active', True),
            }
            question = data.get('uuid') and Questions.search([('uuid', '=', data['uuid'])], limit=1)
            if question and question.template_id == self:
                question.write(vals)
            else:
                # A GUID used by another template's question stays with that
                # one; this template gets the question under a new GUID.
                if data.get('uuid') and not question:
                    vals['uuid'] = data['uuid']
                question = Questions.create(dict(vals, template_id=self.id))
            question._import_options(data.get('options') or [])


class ChecklistQuestion(models.Model):
    _name = 'checklist.question'
    _description = 'Checklist Question'
    _order = 'template_id, sequence, id'

    template_id = fields.Many2one(
        'checklist.template', string='Template', required=True, ondelete='cascade', index=True,
    )
    # Hidden GUID: JSON imports update the question with the same GUID
    # instead of adding a new one.
    uuid = fields.Char(string='GUID', required=True, copy=False, readonly=True, default=_new_uuid)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    name = fields.Char(string='Question Title', required=True, translate=True)
    description = fields.Text(string='Description', translate=True)
    question_type = fields.Selection(
        QUESTION_TYPES, string='Type', required=True, default='buttons',
    )
    option_ids = fields.One2many(
        'checklist.question.option', 'question_id', string='Button Values', copy=True,
        help='The buttons the person filling in the checklist chooses from when the type is Buttons.',
    )

    _uuid_uniq = models.Constraint('UNIQUE (uuid)', 'Another question already has this GUID.')

    def _checklist_line_vals(self):
        self.ensure_one()
        return {
            'question_id': self.id,
            'sequence': self.sequence,
            'name': self.name,
            'description': self.description,
            'question_type': self.question_type,
        }

    def _import_options(self, options_data):
        self.ensure_one()
        Options = self.env['checklist.question.option'].with_context(active_test=False)
        for data in options_data:
            vals = {
                'name': data['name'],
                'sequence': data.get('sequence', 10),
                'color': data.get('color') or False,
                'active': data.get('active', True),
            }
            option = data.get('uuid') and Options.search([('uuid', '=', data['uuid'])], limit=1)
            if option and option.question_id == self:
                option.write(vals)
                continue
            if not option:
                # Files without GUIDs: reuse this question's value of the same name.
                option = Options.search([('question_id', '=', self.id), ('name', '=', data['name'])], limit=1)
                if option and not data.get('uuid'):
                    option.write(vals)
                    continue
                if data.get('uuid'):
                    vals['uuid'] = data['uuid']
            Options.create(dict(vals, question_id=self.id))


class ChecklistQuestionOption(models.Model):
    _name = 'checklist.question.option'
    _description = 'Checklist Button Value'
    _order = 'question_id, sequence, id'

    question_id = fields.Many2one(
        'checklist.question', string='Question', required=True, ondelete='cascade', index=True,
    )
    # Hidden GUID, matched on JSON import like the question's.
    uuid = fields.Char(string='GUID', required=True, copy=False, readonly=True, default=_new_uuid)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    name = fields.Char(string='Value', required=True, translate=True)
    color = fields.Char(
        string='Colour',
        help='Colour of this button on checklists. Leave empty for a plain button.',
    )

    _uuid_uniq = models.Constraint('UNIQUE (uuid)', 'Another button value already has this GUID.')

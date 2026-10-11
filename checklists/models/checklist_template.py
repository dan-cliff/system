# -*- coding: utf-8 -*-
import io
import json
import re
import uuid
import zipfile

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

from .checklist_group_access import CREATE_PERMISSIONS
from .checklist_question_condition import OPERATORS

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
    ('select', 'Single Select Dropdown'),
    ('radio', 'Radio Button'),
    ('multi_select', 'Multi Select Dropdown'),
    ('multi_checkbox', 'Multi Select Checkbox'),
    ('slider', 'Slider Select'),
    ('boolean', 'Boolean Toggle'),
    ('geolocation', 'GeoLocation'),
    ('image', 'Image Upload'),
    ('file', 'File Upload'),
    ('phone', 'Phone Number'),
    ('email', 'Email'),
    ('website', 'Website'),
    ('many2one', 'Many2one'),
    ('many2many', 'Many2Many'),
    ('section_title', 'Section Title'),
    ('section_break', 'Section Break'),
    ('instructions', 'Instructions'),
]
# Types that lay out the form rather than ask for an answer.
LAYOUT_TYPES = ('section_title', 'section_break', 'instructions')
# Technical: the form and PDF draw the Section Break's title from this.
TITLE_POSITIONS = [('above', 'Above the line'), ('below', 'Below the line'), ('none', 'Not shown')]
# Layout settings copied from the question onto checklist lines.
LAYOUT_FIELDS = ('layout_text_color', 'layout_bg_color', 'layout_border_color',
                 'layout_line_color', 'layout_title_position', 'instructions')
# Types answered by picking the question's options (Button Values).
OPTION_TYPES = ('buttons', 'select', 'radio', 'slider', 'multi_select', 'multi_checkbox')
# Types answered by picking records of another model.
RELATION_TYPES = ('many2one', 'many2many')

TEMPLATE_JSON_FORMAT = 'checklists.template'
TEMPLATE_JSON_VERSION = 1
# ESM Measures template exports have the same layout (without GUIDs).
IMPORTABLE_JSON_FORMATS = (TEMPLATE_JSON_FORMAT, 'esm_measures.inspection_template')


def group_panel_range(model, field_name, **kwargs):
    """Side panel values for a Checklist Groups many2many (select="one").

    Odoo only builds a single-choice side panel for many2one and selection
    fields, so the values and counters are built here: a record counts
    under each of its groups.
    """
    domain = Domain.AND([
        Domain(kwargs.get('search_domain') or []),
        Domain(kwargs.get('category_domain') or []),
        Domain(kwargs.get('filter_domain') or []),
    ])
    counts = {group.id: count for group, count in model._read_group(domain, [field_name], ['__count']) if group}
    groups = model.env['checklist.group'].search_read(
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

    # Whether the current user may start checklists from this template.
    can_create_checklist = fields.Boolean(
        compute='_compute_can_create_checklist', search='_search_can_create_checklist',
    )

    _uuid_uniq = models.Constraint('UNIQUE (uuid)', 'Another template already has this GUID.')

    def _creatable_group_ids(self):
        """Checklist Groups whose templates the current user may start checklists
        from, or None for all (Administrators)."""
        if self.env.user.has_group('checklists.group_checklist_admin'):
            return None
        return self.env['checklist.group.access']._user_group_ids(CREATE_PERMISSIONS)

    @api.depends_context('uid')
    def _compute_can_create_checklist(self):
        group_ids = self._creatable_group_ids()
        for template in self:
            template.can_create_checklist = (
                group_ids is None or not template.group_ids
                or bool(set(template.group_ids.ids) & set(group_ids))
            )

    def _search_can_create_checklist(self, operator, value):
        if operator in ('in', 'not in'):
            positive = (True in value) == (operator == 'in')
        elif operator in ('=', '!='):
            positive = bool(value) == (operator == '=')
        else:
            return NotImplemented
        group_ids = self._creatable_group_ids()
        if group_ids is None:
            domain = Domain.TRUE
        else:
            domain = Domain('group_ids', '=', False) | Domain('group_ids', 'in', group_ids)
        return domain if positive else ~domain

    @api.depends('question_ids')
    def _compute_question_count(self):
        for template in self:
            template.question_count = len(template.question_ids)

    # ── Side panel ───────────────────────────────────────────────────────

    @api.model
    def search_panel_select_range(self, field_name, **kwargs):
        if field_name == 'group_ids':
            return group_panel_range(self, field_name, **kwargs)
        return super().search_panel_select_range(field_name, **kwargs)

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
            **self._export_template_settings(),
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
                'relation_model': question.relation_model or '',
                'relation_domain': question.relation_domain or '[]',
                'layout': {name: question[name] or '' for name in LAYOUT_FIELDS},
                'conditions': {
                    'enabled': question.conditional,
                    'logic': question.condition_logic,
                    'user_filter': question.condition_user_domain or '[]',
                    'checklist_filter': question.condition_record_domain or '[]',
                    'rules': [{
                        'question_uuid': condition.source_question_id.uuid,
                        'operator': condition.operator,
                        'value': condition.value or '',
                        'option_uuids': condition.option_ids.mapped('uuid'),
                    } for condition in question.condition_ids],
                },
                'options': [{
                    'uuid': option.uuid,
                    'name': option.name,
                    'sequence': option.sequence,
                    'color': option.color or '',
                    'active': option.active,
                } for option in question.option_ids],
            } for question in questions],
        }

    def _export_template_settings(self):
        """Extra template settings for the JSON export (extended by add-ons)."""
        return {}

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
                if question['question_type'] in RELATION_TYPES and \
                        question.get('relation_model') not in self.env:
                    raise UserError(self.env._(
                        'Question "%(question)s" picks from a model that is not installed here: %(model)s',
                        question=question['name'], model=question.get('relation_model'),
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
                **self._import_template_settings(data),
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

    @api.model
    def _import_template_settings(self, data):
        """Template values from the extra settings of a JSON export
        (extended by add-ons, the counterpart of _export_template_settings)."""
        return {}

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
        # File GUID -> record, for the conditions (which name other questions).
        question_map, option_map, imported = {}, {}, []
        for data in questions_data:
            vals = {
                'name': data['name'],
                'description': data.get('description') or False,
                'question_type': data['question_type'],
                'sequence': data.get('sequence', 10),
                'active': data.get('active', True),
                'relation_model_id': self.env['ir.model']._get_id(data['relation_model'])
                if data.get('relation_model') in self.env else False,
                'relation_domain': data.get('relation_domain') or '[]',
                **{name: (data.get('layout') or {}).get(name) or False
                   for name in LAYOUT_FIELDS if (data.get('layout') or {}).get(name)},
            }
            conditions = data.get('conditions') or {}
            vals.update({
                'conditional': bool(conditions.get('enabled')),
                'condition_logic': conditions.get('logic') if conditions.get('logic') in ('all', 'any') else 'all',
                'condition_user_domain': conditions.get('user_filter') or '[]',
                'condition_record_domain': conditions.get('checklist_filter') or '[]',
            })
            question = data.get('uuid') and Questions.search([('uuid', '=', data['uuid'])], limit=1)
            if question and question.template_id == self:
                question.write(vals)
            else:
                # A GUID used by another template's question stays with that
                # one; this template gets the question under a new GUID.
                if data.get('uuid') and not question:
                    vals['uuid'] = data['uuid']
                question = Questions.create(dict(vals, template_id=self.id))
            option_map.update(question._import_options(data.get('options') or []))
            if data.get('uuid'):
                question_map[data['uuid']] = question
            imported.append((question, data))
        for question, data in imported:
            if 'conditions' not in data:
                continue
            commands = [Command.clear()]
            for rule in (data['conditions'] or {}).get('rules') or []:
                source = question_map.get(rule.get('question_uuid')) or Questions.search(
                    [('uuid', '=', rule.get('question_uuid')), ('template_id', '=', self.id)], limit=1)
                if not source or rule.get('operator') not in dict(OPERATORS):
                    continue
                options = [option_map[u].id for u in rule.get('option_uuids') or [] if u in option_map]
                commands.append(Command.create({
                    'source_question_id': source.id,
                    'operator': rule['operator'],
                    'value': rule.get('value') or False,
                    'option_ids': [Command.set(options)],
                }))
            question.condition_ids = commands


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
        'checklist.question.option', 'question_id', string='Options', copy=True,
        help='The values the person filling in the checklist chooses from (Buttons, dropdowns, '
             'radio buttons, checkboxes and the slider, in this order).',
    )
    # Many2one / Many2Many: the model whose records are picked, and a filter on them.
    relation_model_id = fields.Many2one(
        'ir.model', string='Model', ondelete='cascade',
        domain="[('transient', '=', False), ('abstract', '=', False)]",
        help='The records the person filling in the checklist picks from, e.g. Contact or Employee.',
    )
    relation_model = fields.Char(related='relation_model_id.model', string='Model Name')
    relation_domain = fields.Char(
        string='Filter', default='[]',
        help='Only records matching this filter can be picked.',
    )

    # Section Title / Section Break / Instructions
    layout_text_color = fields.Char(string='Text Colour', default='#1f2937')
    layout_bg_color = fields.Char(string='Background Colour', default='#eef2f7')
    layout_border_color = fields.Char(string='Border Colour', default='#9aa5b1')
    layout_line_color = fields.Char(string='Line Colour', default='#9aa5b1')
    layout_title_position = fields.Selection(
        TITLE_POSITIONS, string='Title', default='above',
        help='Where the Section Break shows its title, if at all.',
    )
    instructions = fields.Html(string='Instructions', translate=True)

    # Conditional display (see checklist_question_condition.py)
    conditional = fields.Boolean(
        string='Conditional Display',
        help='Only show this question on checklists when its conditions are met.',
    )
    condition_logic = fields.Selection(
        [('all', 'All conditions'), ('any', 'Any condition')], string='Show When',
        default='all', required=True,
    )
    condition_ids = fields.One2many(
        'checklist.question.condition', 'question_id', string='Answer Conditions', copy=False,
    )
    condition_user_domain = fields.Char(
        string='Current User', default='[]',
        help='Only shown to users matching this filter (e.g. their groups, job, department).',
    )
    condition_record_domain = fields.Char(
        string='Checklist', default='[]',
        help="Only shown on checklists matching this filter (e.g. the company, organisation "
             "units or asset).",
    )

    _uuid_uniq = models.Constraint('UNIQUE (uuid)', 'Another question already has this GUID.')

    @api.constrains('question_type', 'relation_model_id')
    def _check_relation_model(self):
        for question in self:
            if question.question_type in RELATION_TYPES and not question.relation_model_id:
                raise ValidationError(self.env._('Question "%s" needs a Model to pick records from.', question.name))

    @api.onchange('relation_model_id')
    def _onchange_relation_model_id(self):
        self.relation_domain = '[]'

    def _checklist_line_vals(self):
        self.ensure_one()
        return {
            'question_id': self.id,
            'sequence': self.sequence,
            'name': self.name,
            'description': self.description,
            'question_type': self.question_type,
            'relation_model_id': self.relation_model_id.id,
            'relation_domain': self.relation_domain or '[]',
            **{name: self[name] for name in LAYOUT_FIELDS},
            'conditional': self.conditional,
            'condition_logic': self.condition_logic,
            'condition_rules': self.condition_ids._rule_vals() if self.conditional else [],
            'condition_user_domain': self.condition_user_domain or '[]' if self.conditional else '[]',
            'condition_record_domain': self.condition_record_domain or '[]' if self.conditional else '[]',
        }

    def _import_options(self, options_data):
        self.ensure_one()
        Options = self.env['checklist.question.option'].with_context(active_test=False)
        mapping = {}
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
            else:
                if not option:
                    # Files without GUIDs: reuse this question's value of the same name.
                    option = Options.search([('question_id', '=', self.id), ('name', '=', data['name'])], limit=1)
                    if option and not data.get('uuid'):
                        option.write(vals)
                    else:
                        if data.get('uuid'):
                            vals['uuid'] = data['uuid']
                        option = Options.create(dict(vals, question_id=self.id))
                else:
                    option = Options.create(dict(vals, question_id=self.id))
            if data.get('uuid'):
                mapping[data['uuid']] = option
        return mapping


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

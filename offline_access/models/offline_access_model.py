import hashlib
import json
from datetime import timedelta

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.safe_eval import safe_eval

# Field types the offline screens can show.
SUPPORTED_TYPES = {
    'char', 'text', 'html', 'integer', 'float', 'monetary', 'date', 'datetime',
    'boolean', 'selection', 'many2one', 'one2many', 'many2many',
}
X2MANY_TYPES = {'one2many', 'many2many'}
HIDDEN_VALUES = {'1', 'True', 'true'}
# Widgets whose value still reads well as plain text. A field drawn by any
# other widget (e.g. a body part picker storing JSON) is left out offline.
TEXT_WIDGETS = {
    None, 'char', 'text', 'html', 'email', 'phone', 'url', 'CopyClipboardChar', 'integer', 'float',
    'monetary', 'percentage', 'date', 'datetime', 'boolean', 'boolean_toggle', 'selection', 'radio',
    'selection_badge', 'badge', 'statusbar', 'priority', 'many2one', 'many2one_avatar',
    'many2one_avatar_user', 'many2one_avatar_employee', 'many2many_tags', 'many2many_tags_avatar',
    'many2many_avatar_user', 'many2many_checkboxes', 'one2many', 'many2many',
    'risk_score_badge', 'risk_matrix_selector',
}
MAX_LINES_PER_FIELD = 200
MAX_LIST_COLUMNS = 6
# Records are only re-sent when they change, but a full refresh this often
# also picks up changes Odoo doesn't record on the record itself (e.g. lines).
FULL_REFRESH_AFTER = timedelta(hours=24)
# Changes saved by transactions still running during a sync carry an earlier
# write date than the sync, so each sync looks back this far as well.
SYNC_OVERLAP = timedelta(minutes=5)

# Starting Offline Models for the apps chosen for offline use, added for
# whichever of them is installed: (model, record limit, filter).
SUGGESTED_MODELS = [
    ('risk.assessment', 200, []),
    ('risk.template', 200, []),
    ('incident.report', 200, []),
    ('incident.corrective.action', 300, []),
    ('asset.asset', 1000, []),
    ('asset.defect', 300, []),
    ('asset.maintenance.log', 300, []),
    ('asset.usage.log', 300, []),
    ('zoo.animal', 1000, []),
    ('zoo.enclosure', 500, []),
    ('zoo.feeding', 300, []),
    ('zoo.health.record', 300, []),
    ('zoo.animal.weight', 300, []),
    ('zoo.animal.note', 300, []),
]


def _hidden(node):
    return (node.get('invisible') in HIDDEN_VALUES or node.get('column_invisible') in HIDDEN_VALUES
            or (node.tag == 'field' and node.get('widget') not in TEXT_WIDGETS))


class OfflineAccessModel(models.Model):
    _name = 'offline.access.model'
    _description = 'Offline Model'
    _order = 'sequence, id'

    name = fields.Char(compute='_compute_name', store=True, readonly=False, required=True, precompute=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one(
        'ir.model', string='Model', required=True, ondelete='cascade',
        domain=[('transient', '=', False), ('abstract', '=', False)])
    model_name = fields.Char(related='model_id.model', store=True, string='Technical Name')
    domain = fields.Char(string='Filter', default='[]',
                         help='Which records go offline. Each user only gets the records they can see.')
    record_limit = fields.Integer(string='Record Limit', default=500, required=True,
                                  help='Most records each device keeps, the most recently changed first.')
    field_ids = fields.Many2many(
        'ir.model.fields', 'offline_access_model_field_rel', 'offline_model_id', 'field_id',
        string='Fields', domain="[('model_id', '=', model_id), ('ttype', 'in', %s)]" % sorted(SUPPORTED_TYPES),
        help='Leave empty to show the same fields, in the same sections, as the normal form.')
    list_field_ids = fields.Many2many(
        'ir.model.fields', 'offline_access_model_list_field_rel', 'offline_model_id', 'field_id',
        string='List Columns', domain="[('model_id', '=', model_id), ('ttype', 'in', %s)]" % sorted(SUPPORTED_TYPES),
        help='Leave empty to use the columns of the normal list.')

    _model_uniq = models.Constraint('UNIQUE(model_id)', 'This model is already available offline.')
    _record_limit_positive = models.Constraint('CHECK(record_limit > 0)', 'The record limit must be at least 1.')

    @api.depends('model_id')
    def _compute_name(self):
        for offline_model in self:
            offline_model.name = offline_model.model_id.name or offline_model.name

    @api.constrains('domain', 'model_id')
    def _check_domain(self):
        for offline_model in self:
            try:
                domain = offline_model._get_domain()
                self.env[offline_model.model_name].search_count(domain, limit=1)
            except Exception as e:
                raise ValidationError(self.env._('The filter for %(name)s is not valid: %(error)s',
                                                 name=offline_model.name, error=e)) from e

    def _get_domain(self):
        """The filter, which can refer to the signed in ``user``, ``uid`` and
        ``company_ids`` as record rules can."""
        self.ensure_one()
        eval_context = dict(self.env['ir.rule']._eval_context(), uid=self.env.uid)
        return safe_eval(self.domain or '[]', eval_context)

    @api.model
    def action_add_suggested(self):
        """Add the starting Offline Models for the apps that are installed."""
        existing = set(self.with_context(active_test=False).search([]).mapped('model_name'))
        IrModel = self.env['ir.model']
        sequence = 10
        to_create = []
        for model_name, limit, domain in SUGGESTED_MODELS:
            sequence += 10
            model = IrModel._get(model_name)
            if model and model_name not in existing:
                to_create.append({'model_id': model.id, 'record_limit': limit,
                                  'domain': repr(domain), 'sequence': sequence})
        self.create(to_create)
        return {'type': 'ir.actions.client', 'tag': 'reload'} if to_create else {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'info', 'message': self.env._('All the suggested models are already here.')},
        }

    # ── Layout: what the offline screens show ────────────────────────────────

    def _get_layout(self):
        """The fields, sections and list columns for this model, as the
        current user sees them in the normal form and list views."""
        self.ensure_one()
        Model = self.env[self.model_name]
        fields_info = Model.fields_get(attributes=['string', 'type', 'relation', 'selection', 'digits'])

        def field_meta(name, info, node=None):
            meta = {
                'name': name,
                'string': (node.get('string') if node is not None else None) or info['string'],
                'type': info['type'],
            }
            if info['type'] == 'selection':
                meta['selection'] = info.get('selection') or []
            if info['type'] in ('float', 'monetary') and info.get('digits'):
                meta['digits'] = info['digits'][1]
            if info.get('relation'):
                meta['relation'] = info['relation']
            return meta

        def supported(name):
            return name in fields_info and fields_info[name]['type'] in SUPPORTED_TYPES and name != 'id'

        def sub_columns(node, relation):
            """Columns for lines and tags: the inline list's, else just their name."""
            columns = []
            sub_list = node.find('list')
            if sub_list is not None and relation in self.env:
                sub_info = self.env[relation].fields_get(
                    attributes=['string', 'type', 'relation', 'selection', 'digits'])
                for child in sub_list.iter('field'):
                    name = child.get('name')
                    if (child.getparent() is sub_list and not _hidden(child) and name in sub_info and name != 'id'
                            and sub_info[name]['type'] in SUPPORTED_TYPES - X2MANY_TYPES):
                        columns.append(field_meta(name, sub_info[name], child))
            return columns[:MAX_LIST_COLUMNS]

        sections = []
        seen = set()
        field_nodes = {}

        def add(name, node, section):
            if name in seen or not supported(name):
                return
            seen.add(name)
            meta = field_meta(name, fields_info[name], node)
            if meta['type'] in X2MANY_TYPES:
                meta['columns'] = sub_columns(node, meta.get('relation')) if node is not None else []
            section['fields'].append(meta)
            field_nodes[name] = node

        def walk(node, section):
            for child in node:
                if not isinstance(child.tag, str) or _hidden(child):
                    continue
                if child.tag == 'field':
                    add(child.get('name'), child, section)
                elif child.tag in ('button', 'chatter', 'widget', 'script'):
                    continue
                elif child.tag == 'div' and 'oe_button_box' in (child.get('class') or ''):
                    continue
                elif child.tag in ('page', 'group') and child.get('string'):
                    sub_section = {'title': child.get('string'), 'fields': []}
                    sections.append(sub_section)
                    walk(child, sub_section)
                else:
                    walk(child, section)

        # Users can't read ir.model.fields: only the names are needed here.
        field_names = self.sudo().field_ids.sorted('id').mapped('name')
        list_field_names = self.sudo().list_field_ids.sorted('id').mapped('name')
        if field_names:
            main = {'title': '', 'fields': []}
            sections.append(main)
            for name in field_names:
                add(name, None, main)
        else:
            form_arch = etree.fromstring(Model.get_view(view_type='form')['arch'])
            main = {'title': '', 'fields': []}
            sections.append(main)
            walk(form_arch, main)
        sections = [s for s in sections if s['fields']]

        if list_field_names:
            list_columns = [name for name in list_field_names if supported(name)]
        else:
            list_arch = etree.fromstring(Model.get_view(view_type='list')['arch'])
            list_columns = [
                node.get('name') for node in list_arch.iter('field')
                if node.getparent() is list_arch and not _hidden(node) and supported(node.get('name'))
                and fields_info[node.get('name')]['type'] not in X2MANY_TYPES
            ]
        list_columns = list(dict.fromkeys(list_columns))[:MAX_LIST_COLUMNS]
        for name in list_columns:
            if name not in seen:
                add(name, None, sections[0] if sections else main)
        if not sections:
            sections = [main]

        return {'sections': sections, 'list_columns': list_columns}

    # ── Sync ─────────────────────────────────────────────────────────────────

    def _sync_payload(self, cursor):
        """Records for this model, as the current user. ``cursor`` is what the
        device sent back from the last sync: {'time': ..., 'layout': ...}."""
        self.ensure_one()
        Model = self.env[self.model_name]
        try:
            Model.check_access('read')
        except AccessError:
            return None
        layout = self._get_layout()
        layout_hash = hashlib.sha256(json.dumps(layout, sort_keys=True, default=str).encode()).hexdigest()[:16]
        domain = self._get_domain()
        records = Model.search(domain, limit=self.record_limit, order='write_date desc, id desc')
        now = self.env.cr.now()
        cursor = cursor or {}
        cursor_time = fields.Datetime.to_datetime(cursor.get('time')) if cursor.get('time') else None
        full = (not cursor_time or cursor.get('layout') != layout_hash
                or cursor_time < now - FULL_REFRESH_AFTER)
        changed = records if full else records.filtered(lambda r: r.write_date and r.write_date >= cursor_time)
        return {
            'id': self.id,
            'model': self.model_name,
            'name': self.name,
            'sequence': self.sequence,
            'layout': layout,
            'layout_hash': layout_hash,
            'ids': records.ids,
            'full': full,
            'records': self._read_records(changed, layout),
            'cursor': {'time': fields.Datetime.to_string(now - SYNC_OVERLAP), 'layout': layout_hash},
        }

    def _read_records(self, records, layout):
        if not records:
            return []
        all_fields = [f for section in layout['sections'] for f in section['fields']]
        names = [f['name'] for f in all_fields]
        values = records.read(names + ['display_name'])
        for field in all_fields:
            if field['type'] not in X2MANY_TYPES:
                continue
            sub_ids = list({sub_id for vals in values for sub_id in vals[field['name']][:MAX_LINES_PER_FIELD]})
            sub_values = {}
            if sub_ids and field.get('relation'):
                try:
                    sub_records = self.env[field['relation']].browse(sub_ids)
                    sub_values = {
                        vals['id']: vals for vals in sub_records.read(
                            [c['name'] for c in field['columns']] + ['display_name'])
                    }
                except AccessError:
                    sub_values = {}
            for vals in values:
                ids = vals[field['name']]
                vals[field['name']] = {
                    'count': len(ids),
                    'lines': [sub_values[i] for i in ids[:MAX_LINES_PER_FIELD] if i in sub_values],
                }
        return values

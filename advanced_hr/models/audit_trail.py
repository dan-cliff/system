# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models
from odoo.tools import format_amount, formatLang, html2plaintext

# Fields never listed in the Audit Trail: bookkeeping, chatter and copies of
# other fields (the resized images follow image_1920).
AUDIT_EXCLUDED_FIELDS = {
    'id', 'create_uid', 'create_date', 'write_uid', 'write_date', 'display_name',
    'parent_path', 'last_modified_date', 'last_modified_uid',
    'resource_id', 'version_id', 'current_version_id',
    'image_1024', 'image_512', 'image_256', 'image_128',
    'avatar_1920', 'avatar_1024', 'avatar_512', 'avatar_256', 'avatar_128',
    'work_permit_scheduled_activity',
}
AUDIT_EXCLUDED_PREFIXES = ('message_', 'activity_', 'website_message', 'rating_', 'org_show_')

# Pending changes of the current transaction, in cr.precommit.data.
PRECOMMIT_KEY = 'advanced_hr.audit_trail'


class AdvancedHrAuditTrail(models.Model):
    _name = 'advanced.hr.audit.trail'
    _description = 'Audit Trail'
    _order = 'date desc, id desc'
    _rec_name = 'record_name'

    date = fields.Datetime(string='Changed At', required=True, readonly=True, index=True,
                           default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string='Changed By', readonly=True, index=True,
                              ondelete='set null')
    operation = fields.Selection([
        ('create', 'Created'),
        ('write', 'Updated'),
        ('unlink', 'Deleted'),
    ], string='Change', required=True, readonly=True)
    res_model = fields.Char(string='Model', required=True, readonly=True, index=True)
    res_model_name = fields.Char(string='Record Type', readonly=True)
    res_id = fields.Integer(string='Record ID', readonly=True, index=True)
    record_name = fields.Char(string='Record', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True, index=True,
                                  ondelete='set null')
    department_id = fields.Many2one('hr.department', string='Department', readonly=True, index=True,
                                    ondelete='set null')
    company_id = fields.Many2one('res.company', string='Company', readonly=True, index=True,
                                 ondelete='set null')
    line_ids = fields.One2many('advanced.hr.audit.trail.line', 'audit_id', string='Changes', readonly=True)
    change_count = fields.Integer(string='Fields Changed', compute='_compute_change_count')
    changed_fields = fields.Char(string='Changed Fields', compute='_compute_change_count')

    @api.depends('line_ids')
    def _compute_change_count(self):
        for entry in self:
            entry.change_count = len(entry.line_ids)
            entry.changed_fields = ', '.join(entry.line_ids.mapped('field_label'))

    def action_open_record(self):
        self.ensure_one()
        record = self.env[self.res_model].browse(self.res_id).exists() if self.res_model in self.env else False
        if not record:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': record.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'context': {'personnel_app': True},
        }


class AdvancedHrAuditTrailLine(models.Model):
    _name = 'advanced.hr.audit.trail.line'
    _description = 'Audit Trail Change'
    _order = 'audit_id, sequence, id'

    audit_id = fields.Many2one('advanced.hr.audit.trail', string='Audit Trail Entry', required=True,
                               ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    field_name = fields.Char(string='Technical Name', readonly=True)
    field_label = fields.Char(string='Field', readonly=True)
    old_value = fields.Text(string='Original Value', readonly=True)
    new_value = fields.Text(string='New Value', readonly=True)
    date = fields.Datetime(related='audit_id.date', string='Changed At')
    user_id = fields.Many2one(related='audit_id.user_id', string='Changed By')


class AdvancedHrAuditMixin(models.AbstractModel):
    """Records one Audit Trail entry per record for each save (transaction),
    listing only the fields whose value changed, with the original and the
    new value. Replaces chatter tracking on the models that use it."""
    _name = 'advanced.hr.audit.mixin'
    _description = 'Personnel Audit Trail Mixin'

    # Chatter tracking is replaced by the Audit Trail.
    def _track_get_fields(self):
        return set()

    @api.model
    def _audit_field_names(self, names):
        result = []
        for name in names:
            field = self._fields.get(name)
            if (not field or name in AUDIT_EXCLUDED_FIELDS or name.startswith(AUDIT_EXCLUDED_PREFIXES)
                    or not (field.store or field.inherited) or field.type == 'properties_definition'):
                continue
            result.append(name)
        return result

    # ── Values ────────────────────────────────────────────────────────────

    def _audit_raw_value(self, name):
        """A comparable form of the field's value."""
        self.ensure_one()
        field = self._fields[name]
        value = self[name]
        if field.type == 'many2one':
            return value.id
        if field.type in ('one2many', 'many2many'):
            return tuple(sorted(value.ids))
        if field.type in ('json', 'properties'):
            return json.dumps(value, sort_keys=True, default=str)
        if field.type == 'binary':
            return value or False
        return value

    def _audit_display_value(self, name):
        """The field's value as people read it (dd/mm/yyyy dates)."""
        self.ensure_one()
        field = self._fields[name]
        value = self[name]
        if field.type == 'many2one':
            return value.display_name or ''
        if field.type in ('one2many', 'many2many'):
            return ', '.join(name for name in value.mapped('display_name') if name)
        if field.type == 'boolean':
            return self.env._('Yes') if value else self.env._('No')
        if value is False or value is None or value == '':
            return ''
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, value)
        if field.type == 'date':
            return value.strftime('%d/%m/%Y')
        if field.type == 'datetime':
            return fields.Datetime.context_timestamp(self, value).strftime('%d/%m/%Y %H:%M')
        if field.type == 'monetary':
            currency = self[field.get_currency_field(self)] if field.get_currency_field(self) else False
            return format_amount(self.env, value, currency) if currency else formatLang(self.env, value)
        if field.type == 'float':
            return formatLang(self.env, value, digits=field.get_digits(self.env)[1] if field.get_digits(self.env) else 2)
        if field.type == 'html':
            return html2plaintext(value or '').strip()
        if field.type == 'binary':
            return self.env._('(file)')
        if field.type == 'properties':
            return '; '.join(
                '%s: %s' % (prop.get('string'), prop.get('value'))
                for prop in (value or []) if prop.get('value') not in (False, None, '')
            )
        if field.type == 'json':
            return json.dumps(value, default=str)
        return str(value)

    # ── Collecting changes ────────────────────────────────────────────────

    def _audit_pending(self):
        data = self.env.cr.precommit.data
        if PRECOMMIT_KEY not in data:
            data[PRECOMMIT_KEY] = {}
            self.env.cr.precommit.add(self._audit_flush)
        return data[PRECOMMIT_KEY]

    def _audit_skip(self):
        return self.env.context.get('advanced_hr_audit_disable') or self.env.context.get('install_mode')

    def _audit_remember(self, operation, names):
        pending = self._audit_pending()
        for record in self.sudo().with_context(active_test=False):
            key = (record._name, record.id)
            entry = pending.get(key)
            if entry is None:
                entry = pending[key] = {
                    'operation': operation,
                    'uid': self.env.uid,
                    'date': fields.Datetime.now(),
                    'values': {},
                }
            if operation == 'create':
                # Writes made while creating the record are part of creating it.
                entry['operation'] = 'create'
                entry['values'] = dict.fromkeys(set(entry['values']) | set(names), (False, ''))
                continue
            for name in names:
                if name in entry['values']:
                    continue
                if entry['operation'] == 'create':
                    entry['values'][name] = (False, '')
                else:
                    entry['values'][name] = (record._audit_raw_value(name), record._audit_display_value(name))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self._audit_skip():
            for record, vals in zip(records, vals_list):
                record._audit_remember('create', self._audit_field_names(vals))
        return records

    def write(self, vals):
        if self._audit_skip() or not self:
            return super().write(vals)
        names = self._audit_field_names(vals)
        if names:
            self._audit_remember('write', names)
        return super().write(vals)

    def unlink(self):
        if not self._audit_skip():
            pending = self._audit_pending()
            Audit = self.env['advanced.hr.audit.trail'].sudo()
            for record in self.sudo():
                pending.pop((record._name, record.id), None)
                Audit.create(record._audit_entry_vals('unlink', self.env.uid, fields.Datetime.now()))
        return super().unlink()

    def _audit_entry_vals(self, operation, uid, date):
        self.ensure_one()
        vals = {
            'operation': operation,
            'user_id': uid,
            'date': date,
            'res_model': self._name,
            'res_model_name': self.env['ir.model']._get(self._name).name,
            'res_id': self.id,
            'record_name': self.display_name,
            'company_id': self.company_id.id if 'company_id' in self._fields else False,
        }
        if self._name == 'hr.employee':
            vals['employee_id'] = self.id
        elif self._name == 'hr.department':
            vals['department_id'] = self.id
        return vals

    def _audit_flush(self):
        pending = self.env.cr.precommit.data.pop(PRECOMMIT_KEY, {})
        if not pending:
            return
        Audit = self.env['advanced.hr.audit.trail'].sudo()
        vals_list = []
        for (model_name, res_id), entry in pending.items():
            record = self.env[model_name].sudo().with_context(active_test=False).browse(res_id).exists()
            if not record:
                continue
            lines = []
            for sequence, (name, (old_raw, old_display)) in enumerate(entry['values'].items()):
                if name not in record._fields:
                    continue
                new_raw = record._audit_raw_value(name)
                if entry['operation'] == 'create':
                    if new_raw in (False, None, '', (), 0) and record._fields[name].type != 'boolean':
                        continue
                    if record._fields[name].type == 'boolean' and not new_raw:
                        continue
                elif new_raw == old_raw:
                    continue
                lines.append((0, 0, {
                    'sequence': sequence,
                    'field_name': name,
                    'field_label': record._fields[name]._description_string(self.env),
                    'old_value': old_display,
                    'new_value': record._audit_display_value(name),
                }))
            if not lines and entry['operation'] != 'create':
                continue
            vals = record._audit_entry_vals(entry['operation'], entry['uid'], entry['date'])
            vals['line_ids'] = lines
            vals_list.append(vals)
        if vals_list:
            Audit.create(vals_list)
        self.env.flush_all()

    def web_read(self, specification):
        # Saving a form reads it back before the transaction commits: write
        # the save's Audit Trail entry first so the form's count includes it.
        if 'personnel_audit_count' in specification and self.env.cr.precommit.data.get(PRECOMMIT_KEY):
            self._audit_flush()
        return super().web_read(specification)

    def action_open_audit_trail(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('advanced_hr.action_audit_trail')
        action['domain'] = [('res_model', '=', self._name), ('res_id', '=', self.id)]
        action['context'] = {'create': False}
        action['display_name'] = self.env._('Audit Trail: %s', self.display_name)
        return action

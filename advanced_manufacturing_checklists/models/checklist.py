# -*- coding: utf-8 -*-
import base64
import binascii
import re
from datetime import datetime, timezone

import pytz

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

# Questions picking a record of these models are filled in from the work order.
PREFILL_MODELS = {
    'product.product': 'product',
    'product.template': 'product_tmpl',
    'mrp.production': 'production',
    'mrp.workorder': 'workorder',
    'mrp.workcenter': 'workcenter',
    'hr.employee': 'employee',
    'stock.lot': 'lot',
}
# Text questions named like these are filled in with the record's name.
PREFILL_TEXT_NAMES = {
    'product': ('product', 'product name', 'item', 'product manufactured', 'product made'),
    'lot': ('lot', 'lot number', 'lot no', 'batch', 'batch number', 'batch no', 'batch code', 'serial',
            'serial number', 'serial no', 'lot serial number', 'lot serial'),
    'production': ('manufacturing order', 'mo', 'mo number', 'production order', 'job', 'job number',
                   'order', 'order number'),
    'workorder': ('work order', 'operation'),
    'workcenter': ('work centre', 'work center', 'workstation', 'work station', 'machine', 'production line'),
    'employee': ('operator', 'worker', 'employee', 'inspector', 'checked by', 'inspected by', 'completed by',
                 'made by', 'produced by'),
}
QUANTITY_NAMES = ('quantity', 'qty', 'quantity produced', 'qty produced', 'batch size', 'units', 'units produced')
DATE_NAMES = ('date', 'production date', 'manufacture date', 'manufacturing date', 'date of manufacture',
              'inspection date', 'date made', 'qa date', 'check date')
DATETIME_NAMES = DATE_NAMES + ('date time', 'date and time', 'time')
TEXT_TYPES = {'text': 'value_text', 'text_area': 'value_text_area', 'phone': 'value_phone',
              'email': 'value_email', 'website': 'value_url'}
SINGLE_OPTION_TYPES = ('buttons', 'select', 'radio', 'slider')
MULTI_OPTION_TYPES = ('multi_select', 'multi_checkbox')


def _normal(name):
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', (name or '').lower()).split())


def prefill_key(question):
    """How the Work Centre app fills in a question, or None."""
    kind = question.question_type
    if kind in ('many2one', 'many2many'):
        return PREFILL_MODELS.get(question.relation_model_id.model)
    name = _normal(question.name)
    if kind == 'text':
        for key, names in PREFILL_TEXT_NAMES.items():
            if name in names:
                return 'text_' + key
    if kind in ('number', 'integer') and name in QUANTITY_NAMES:
        return 'quantity'
    if kind == 'date' and name in DATE_NAMES:
        return 'date'
    if kind == 'datetime' and name in DATETIME_NAMES:
        return 'datetime'
    return None


class Checklist(models.Model):
    _inherit = 'checklist.checklist'

    production_id = fields.Many2one(
        'mrp.production', string='Manufacturing Order', tracking=True, ondelete='set null', index='btree_not_null',
        help='The manufacturing order this QA check was done for.',
    )
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order', ondelete='set null')
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Centre', ondelete='set null')
    mrp_product_id = fields.Many2one(
        'product.product', string='Product', tracking=True, ondelete='set null', index='btree_not_null',
        help='The product made.',
    )
    mrp_lot_ids = fields.Many2many(
        'stock.lot', 'checklist_checklist_mrp_lot_rel', 'checklist_id', 'lot_id',
        string='Lots / Serial Numbers', help='The lots / serial numbers produced by the manufacturing order.',
    )
    mrp_employee_id = fields.Many2one(
        'hr.employee', string='Worker', ondelete='set null',
        help='Who filled in the QA check on the Work Centre app.',
    )

    @api.onchange('production_id')
    def _onchange_production_id_qa(self):
        if self.production_id:
            self.mrp_product_id = self.production_id.product_id
            self.mrp_lot_ids = self.production_id.lot_producing_ids

    # ── Created from the Work Centre app ───────────────────────────────────
    @api.model
    def _mrp_prefill_values(self, workorder, employee, when):
        """What each prefill key stands for on this work order."""
        production = workorder.production_id
        tz = pytz.timezone(workorder.workcenter_id.resource_calendar_id.tz or employee.tz or 'UTC')
        local = pytz.utc.localize(when).astimezone(tz)
        lot = production.lot_producing_ids[:1]
        return {
            'product': production.product_id,
            'product_tmpl': production.product_id.product_tmpl_id,
            'production': production,
            'workorder': workorder,
            'workcenter': workorder.workcenter_id,
            'employee': employee,
            'lot': lot,
            'quantity': production.qty_producing or production.product_qty,
            'date': local.date(),
            'datetime': when,
        }

    def _mrp_prefill_line(self, line, key, values):
        question = line.question_id
        if key.startswith('text_'):
            record = values.get(key[5:])
            if record:
                line.value_text = record.name if record._name != 'mrp.workorder' else record.display_name
            return
        value = values.get(key)
        if not value and value != 0:
            return
        if key == 'quantity':
            if question.question_type == 'integer':
                line.value_integer = int(value)
            else:
                line.value_number = value
        elif key == 'date':
            line.value_date = value
        elif key == 'datetime':
            line.value_datetime = value
        elif question.question_type == 'many2one':
            line.value_reference = f'{value._name},{value.id}'
        elif question.question_type == 'many2many':
            line.value_reference_ids = value.ids

    def _mrp_apply_answer(self, line, answer):
        """An answer from the Work Centre app's QA form, onto a checklist line."""
        kind = line.question_type
        if not isinstance(answer, dict):
            return
        value = answer.get('value')
        if kind in TEXT_TYPES:
            line[TEXT_TYPES[kind]] = str(value or '')[:10000] or False
        elif kind == 'number':
            try:
                line.value_number = float(value or 0)
            except (TypeError, ValueError):
                pass
        elif kind == 'integer':
            try:
                line.value_integer = int(float(value or 0))
            except (TypeError, ValueError):
                pass
        elif kind == 'boolean':
            line.value_boolean = bool(value)
        elif kind in ('date', 'datetime') and value:
            try:
                parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            except ValueError:
                return
            if kind == 'date':
                line.value_date = parsed.date()
            else:
                if parsed.tzinfo:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                line.value_datetime = parsed.replace(microsecond=0)
        elif kind in SINGLE_OPTION_TYPES:
            option = line.question_id.option_ids.filtered(lambda o: o.id == answer.get('option_id'))
            line.value_option_id = option[:1]
        elif kind in MULTI_OPTION_TYPES:
            wanted = set(answer.get('option_ids') or [])
            line.value_option_ids = [Command.set(line.question_id.option_ids.filtered(lambda o: o.id in wanted).ids)]
        elif kind == 'geolocation':
            try:
                line.value_latitude = float(answer.get('lat') or 0)
                line.value_longitude = float(answer.get('lng') or 0)
            except (TypeError, ValueError):
                pass
        elif kind in ('image', 'file') and answer.get('data'):
            try:
                base64.b64decode(answer['data'], validate=True)
            except (binascii.Error, ValueError):
                return
            if kind == 'image':
                line.value_image = answer['data']
            else:
                line.value_file = answer['data']
                line.value_file_name = str(answer.get('name') or 'file')[:200]

    @api.model
    def _mrp_create_from_terminal(self, workorder, employee, when, event):
        production = workorder.production_id
        company = workorder.workcenter_id._terminal_company()
        try:
            template_id = int(event.get('template_id') or 0)
        except (TypeError, ValueError):
            template_id = 0
        template = self.env['checklist.template'].browse(template_id).exists()
        if not template or not template.active or not (template.group_ids & company.mrp_qa_checklist_group_ids):
            raise UserError(self.env._('This QA checklist is not available at the work centre any more.'))
        tz = pytz.timezone(workorder.workcenter_id.resource_calendar_id.tz or employee.tz or 'UTC')
        vals = {
            'template_id': template.id,
            'company_id': production.company_id.id,
            'checklist_date': pytz.utc.localize(when).astimezone(tz).date(),
            'user_id': (employee.user_id or production.user_id or self.env.ref('base.user_root')).id,
            'production_id': production.id,
            'workorder_id': workorder.id,
            'workcenter_id': workorder.workcenter_id.id,
            'mrp_product_id': production.product_id.id,
            'mrp_lot_ids': [Command.set(production.lot_producing_ids.ids)],
            'mrp_employee_id': employee.id,
        }
        # With Organisation Structure: the order's units.
        for name in ('org_division_id', 'org_business_unit_id', 'org_location_id', 'org_department_id'):
            if name in self._fields and name in production._fields:
                vals[name] = production[name].id
        checklist = self.create(vals)
        values = self._mrp_prefill_values(workorder, employee, when)
        answers = event.get('answers') if isinstance(event.get('answers'), dict) else {}
        for line in checklist.line_ids.filtered('question_id'):
            key = prefill_key(line.question_id)
            if key:
                checklist._mrp_prefill_line(line, key, values)
            answer = answers.get(str(line.question_id.id))
            if answer is not None:
                checklist._mrp_apply_answer(line, answer)
        checklist.message_post(body=self.env._(
            'Filled in on the Work Centre app at %(workcenter)s by %(employee)s.',
            workcenter=workorder.workcenter_id.name, employee=employee.name))
        if event.get('state') == 'done':
            checklist.action_complete()
        return checklist

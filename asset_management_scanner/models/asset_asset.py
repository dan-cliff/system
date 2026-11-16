# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# What each kind of bulk log creates: the model, the asset feature it needs
# (as on the asset form) and the fields filled in once for every asset, in
# the order they show on the Scanner. The Asset itself comes from the scans.
BULK_KINDS = {
    'maintenance': {
        'model': 'asset.maintenance.log',
        'feature': 'eff_maintenance',
        'fields': [
            'date', 'date_due', 'maintenance_type_id', 'performed_by', 'performed_by_name',
            'supplier_id', 'cost', 'next_due_date', 'next_due_reading', 'description', 'parts_used',
        ],
    },
    'usage': {
        'model': 'asset.usage.log',
        'feature': 'eff_usage_tracking',
        'fields': ['date', 'user_id', 'reading', 'notes'],
    },
    'defect': {
        'model': 'asset.defect',
        'feature': False,
        'fields': [
            'date', 'date_due', 'severity_id', 'reported_by', 'reported_by_name', 'state',
            'resolved_date', 'description', 'resolution_notes',
        ],
    },
}

# Fields only shown (and saved) when another field has a value.
SHOW_IF = {
    'resolved_date': ('state', 'resolved'),
    'resolution_notes': ('state', 'resolved'),
}

# Small option lists offered as a drop-down; other Many2ones get a search box.
SELECT_MODELS = ('asset.maintenance.type', 'asset.defect.severity')

# Text fields shown as a full-width box.
WIDE_TYPES = ('text', 'html')

CP_URL_RE = re.compile(r'/asset/cp/([^/?#\s]+)')


class Asset(models.Model):
    _inherit = 'asset.asset'

    # ── Finding an asset from a scan ───────────────────────────────────────
    @api.model
    def _scanner_search_asset(self, code):
        """The asset a scanned label stands for: its Control Plane QR code
        (URL or token), Asset #, Serial / VIN, Registration Number or name."""
        code = (code or '').strip()
        if not code:
            return self.browse()
        match = CP_URL_RE.search(code)
        token = match.group(1) if match else code
        for domain in (
            [('cp_token', '=', token)],
            [('asset_number', '=ilike', code)],
            [('serial_number', '=ilike', code)],
            [('registration_number', '=ilike', code)],
            [('name', '=ilike', code)],
        ):
            asset = self.search(domain, limit=2)
            if len(asset) == 1:
                return asset
        return self.browse()

    def _scanner_asset_data(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'asset_number': self.asset_number or '',
            'type': self.asset_subtype_id.display_name or self.asset_type_id.display_name or '',
            'reading': self.latest_usage_reading,
            'unit': self.usage_unit_id.short_code or self.usage_unit_id.name or '',
        }

    @api.model
    def scanner_find_asset(self, code):
        """Look Up: the asset a scanned label stands for, or False."""
        return self._scanner_search_asset(code).id or False

    def action_return_to_scanner(self):
        """Back to the Scanner from an asset opened by Look Up (the record is
        saved by the button first)."""
        return {'type': 'ir.actions.act_url', 'url': '/odoo/scanner', 'target': 'self'}

    # ── Bulk logs ──────────────────────────────────────────────────────────
    @api.model
    def _scanner_bulk_kind(self, kind):
        spec = BULK_KINDS.get(kind)
        if not spec:
            raise UserError(_('Unknown kind of asset log: %s.', kind))
        return spec

    @api.model
    def _scanner_bulk_label(self, kind):
        return {
            'maintenance': _('Maintenance Log'),
            'usage': _('Usage Log'),
            'defect': _('Defect Report'),
        }[kind]

    @api.model
    def scanner_bulk_setup(self, kind):
        """The form the Scanner shows for a bulk log: its fields (label, type,
        required, options) and their default values."""
        spec = self._scanner_bulk_kind(kind)
        Model = self.env[spec['model']]
        descriptions = Model.fields_get(spec['fields'], ['string', 'type', 'required', 'selection'])
        defaults = Model.default_get(spec['fields'])
        result = []
        for name in spec['fields']:
            field = Model._fields[name]
            info = descriptions[name]
            item = {
                'name': name,
                'string': info['string'],
                'required': bool(info.get('required')),
                'wide': field.type in WIDE_TYPES,
                'show_if': list(SHOW_IF[name]) if name in SHOW_IF else False,
            }
            if field.type == 'many2one' and field.comodel_name in SELECT_MODELS:
                options = self.env[field.comodel_name].search([])
                item.update(type='select', options=[[o.id, o.display_name] for o in options])
            elif field.type == 'many2one':
                domain = field.domain if isinstance(field.domain, list) else []
                item.update(type='record', model=field.comodel_name, domain=domain)
            elif field.type == 'selection':
                item.update(type='selection', options=info['selection'])
            elif field.type in ('float', 'integer', 'monetary'):
                item.update(type='number')
            elif field.type in ('date', 'datetime'):
                item.update(type='date')
            else:
                item.update(type='text' if field.type in WIDE_TYPES else 'char')
            value = defaults.get(name, False)
            if field.type == 'date' and value:
                value = fields.Date.to_string(value)
            item['default'] = value
            result.append(item)
        return {'kind': kind, 'label': self._scanner_bulk_label(kind), 'fields': result}

    @api.model
    def scanner_bulk_find_asset(self, kind, code):
        """Scan for a bulk log: the asset's details, or {'error': ...}."""
        spec = self._scanner_bulk_kind(kind)
        asset = self._scanner_search_asset(code)
        if not asset:
            return {'error': _('No asset found for "%s".', (code or '').strip())}
        if spec['feature'] and not asset[spec['feature']]:
            if kind == 'usage':
                return {'error': _('%s does not track usage.', asset.display_name)}
            return {'error': _('%s does not have maintenance enabled.', asset.display_name)}
        return asset._scanner_asset_data()

    @api.model
    def scanner_bulk_generate(self, kind, asset_ids, values):
        """Create one log of this kind per asset, all with the same values.
        Returns how many were created."""
        spec = self._scanner_bulk_kind(kind)
        Model = self.env[spec['model']]
        assets = self.browse(asset_ids).exists()
        if not assets:
            raise UserError(_('Scan at least one asset first.'))
        if spec['feature']:
            missing = assets.filtered(lambda a: not a[spec['feature']])
            if missing:
                raise UserError(_('These assets cannot have a %(log)s: %(assets)s.',
                                  log=self._scanner_bulk_label(kind),
                                  assets=', '.join(missing.mapped('display_name'))))
        values = values or {}
        vals = {}
        for name in spec['fields']:
            if name in SHOW_IF:
                other, wanted = SHOW_IF[name]
                if values.get(other) != wanted:
                    continue
            if name not in values:
                continue
            value = values[name]
            field = Model._fields[name]
            if field.type == 'many2one':
                value = int(value) if value else False
            elif field.type in ('float', 'monetary'):
                value = float(value or 0)
            elif field.type == 'integer':
                value = int(value or 0)
            elif not value:
                value = False
            vals[name] = value
        missing = [Model._fields[name].string for name in spec['fields']
                   if Model._fields[name].required and name not in SHOW_IF
                   and vals.get(name) in (None, False, '')
                   and Model._fields[name].type not in ('float', 'integer', 'monetary')]
        if missing:
            raise UserError(_('Fill in %s first.', ', '.join(missing)))
        records = Model.create([dict(vals, asset_id=asset.id) for asset in assets])
        return {'count': len(records), 'label': self._scanner_bulk_label(kind)}

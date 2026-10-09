import hashlib
import json
import logging
from datetime import timedelta

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.safe_eval import safe_eval

from odoo.addons.web.controllers.utils import clean_action

_logger = logging.getLogger(__name__)

X2MANY_TYPES = {'one2many', 'many2many'}
# Too large to keep on every device: shown as empty offline.
SKIPPED_TYPES = {'binary', 'image'}
# Fields widgets often need without the view listing them.
EXTRA_FIELDS = ('display_name', 'currency_id', 'company_id', 'write_date')
VIEW_TYPES_WITH_DATA = ('list', 'form', 'kanban')
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

    # ── Views: what the web client needs to show the records offline ────────

    def _get_offline_views(self):
        """The actions that open this model from the menus the current user
        can see, and their views as ``get_views`` returns them, so the web
        client can open the normal screens without the server. Returns the
        actions, a bundle of views per action, and the fields of the models
        the views use."""
        self.ensure_one()
        Model = self.env[self.model_name]
        Menu = self.env['ir.ui.menu']
        menus = Menu.browse(Menu._visible_menu_ids())
        actions = self.env['ir.actions.act_window']
        for menu in menus:
            action = menu.sudo().action
            if action and action._name == 'ir.actions.act_window' and action.res_model == self.model_name:
                actions |= action
        default_views = [[False, 'list'], [False, 'form'], [False, 'search']]
        results = [(False, default_views, Model.get_views(default_views, {'load_filters': True, 'toolbar': True}))]
        action_dicts = []
        for action in actions.sorted('id'):
            try:
                action_dict = clean_action(action._get_action_dict(), env=self.env)
                views = [list(view) for view in action_dict.get('views') or []]
                search_view = action_dict.get('search_view_id')
                views.append([search_view[0] if isinstance(search_view, (list, tuple)) else search_view or False,
                              'search'])
                result = Model.with_context(**self._view_refs(action_dict)).get_views(
                    views, {'action_id': action.id, 'load_filters': True, 'toolbar': True})
            except Exception:  # noqa: BLE001 - one broken action shouldn't stop the others
                _logger.warning("Offline Access: can't prepare action %s offline", action.id, exc_info=True)
                continue
            action_dicts.append(action_dict)
            results.append((action.id, views, result))
        # The fields of every model involved, once, rather than in each bundle.
        models_info = {}
        for __, __, result in results:
            for model_name, info in result.get('models', {}).items():
                models_info.setdefault(model_name, {}).setdefault('fields', {}).update(info.get('fields', {}))
        bundles = [{'action_id': action_id, 'views': views, 'result': {'views': result['views']}}
                   for action_id, views, result in results]
        return action_dicts, bundles, models_info

    def _view_refs(self, action_dict):
        """The ``*_view_ref`` keys of an action's context, which pick its views."""
        context = action_dict.get('context') or {}
        if isinstance(context, str):
            try:
                context = safe_eval(context, dict(self.env['ir.rule']._eval_context(), uid=self.env.uid,
                                                  active_id=False, active_ids=[], context={}))
            except Exception:  # noqa: BLE001 - only used to choose views
                context = {}
        return {key: value for key, value in context.items() if key.endswith('_view_ref')}

    def _get_specification(self, bundles, models):
        """The ``web_read`` specification for every field the views show,
        including their lines' fields, as the web client asks for them."""
        self.ensure_one()
        models_info = {name: info.get('fields', {}) for name, info in models.items()}

        def merge(target, source):
            for name, sub in source.items():
                if name in target and isinstance(target[name], dict):
                    if 'fields' in sub:
                        merge(target[name].setdefault('fields', {}), sub['fields'])
                else:
                    target[name] = sub
            return target

        def field_nodes(node):
            for child in node:
                if not isinstance(child.tag, str):
                    continue
                if child.tag == 'field':
                    yield child
                else:
                    yield from field_nodes(child)

        def view_spec(node, model_name):
            fields_info = models_info.get(model_name, {})
            spec = {}
            for field_node in field_nodes(node):
                info = fields_info.get(field_node.get('name'))
                if not info or info['type'] in SKIPPED_TYPES:
                    continue
                if info['type'] == 'many2one':
                    field_spec = {'fields': {'display_name': {}}}
                elif info['type'] in X2MANY_TYPES:
                    sub_spec = {'display_name': {}}
                    for sub_view in field_node:
                        if isinstance(sub_view.tag, str) and sub_view.tag in VIEW_TYPES_WITH_DATA:
                            merge(sub_spec, view_spec(sub_view, info.get('relation')))
                    field_spec = {'fields': sub_spec}
                else:
                    field_spec = {}
                merge(spec, {field_node.get('name'): field_spec})
            return spec

        spec = {}
        for bundle in bundles:
            for view_type, view in bundle['result'].get('views', {}).items():
                if view_type in VIEW_TYPES_WITH_DATA:
                    merge(spec, view_spec(etree.fromstring(view['arch']), self.model_name))
        fields_info = models_info.get(self.model_name, {})
        for name in EXTRA_FIELDS:
            if name in fields_info and name not in spec:
                spec[name] = {'fields': {'display_name': {}}} if fields_info[name]['type'] == 'many2one' else {}
        return spec

    # ── Sync ─────────────────────────────────────────────────────────────────

    def _sync_payload(self, cursor):
        """Records for this model, as the current user, in the shape the web
        client reads them. ``cursor`` is what the device sent back from the
        last sync: {'time': ..., 'layout': ...}. The views and actions are only
        sent when they changed (or on the daily full sync)."""
        self.ensure_one()
        Model = self.env[self.model_name]
        try:
            Model.check_access('read')
        except AccessError:
            return None
        actions, bundles, models = self._get_offline_views()
        spec = self._get_specification(bundles, models)
        meta = {'spec': spec, 'order': Model._order, 'actions': actions, 'bundles': bundles, 'models': models}
        layout_hash = hashlib.sha256(json.dumps(meta, sort_keys=True, default=str).encode()).hexdigest()[:16]
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
            'meta': meta if full else None,
            'ids': records.ids,
            'full': full,
            'records': changed.web_read(spec) if changed else [],
            'cursor': {'time': fields.Datetime.to_string(now - SYNC_OVERLAP), 'layout': layout_hash},
        }

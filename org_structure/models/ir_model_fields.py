"""Add the Organisation fields to the primary models of every installed app.

A primary model is one opened from an app's menus outside its
Configuration / Settings menus. The fields are added while the registry
builds each model, so they reach core and custom apps alike, including apps
installed later (the registry is rebuilt after every install).
"""
import logging

from odoo import models
from odoo.tools import sql

from .org_scope_mixin import ORG_FIELD_NAMES, ORG_SCOPE_METHODS, OrgScopeMixin, org_scope_fields

_logger = logging.getLogger(__name__)

# Menus whose models are option lists / setup, not primary records.
CONFIG_MENU_NAMES = {'configuration', 'settings'}

# Technical and identity models are never scoped. res.partner in particular:
# res.users inherits it, so scoping partners could hide users from
# themselves and lock people out.
EXCLUDED_PREFIXES = ('ir.', 'res.', 'mail.', 'bus.', 'base.', 'base_', 'web.', 'web_', 'org.')


def _primary_models(env):
    """Names of models opened from app menus outside Configuration/Settings."""
    registry = env.registry
    key = frozenset(registry._init_modules)
    cached = getattr(registry, '_org_primary_models', None)
    if cached and cached[0] == key:
        return cached[1]
    cr = env.cr
    primary = set()
    # Nothing to do until org_structure's own tables exist (i.e. mid-install).
    tables = ('ir_ui_menu', 'ir_act_window', 'org_division', 'org_business_unit',
              'org_location', 'org_department')
    if all(sql.table_exists(cr, table) for table in tables):
        cr.execute("SELECT id, parent_id, name->>'en_US' FROM ir_ui_menu WHERE active")
        menus = {mid: (parent_id, (name or '').strip().lower()) for mid, parent_id, name in cr.fetchall()}
        # Models behind window actions, and behind server actions (some apps,
        # e.g. Inventory's Receipts, open their lists through one).
        cr.execute("""
            SELECT m.id, a.res_model
              FROM ir_ui_menu m
              JOIN ir_act_window a ON m.action = 'ir.actions.act_window,' || a.id
             WHERE m.active AND a.res_model IS NOT NULL
             UNION
            SELECT m.id, im.model
              FROM ir_ui_menu m
              JOIN ir_act_server s ON m.action = 'ir.actions.server,' || s.id
              JOIN ir_model im ON im.id = s.model_id
             WHERE m.active
        """)
        for menu_id, res_model in cr.fetchall():
            node, under_config = menu_id, False
            while node:
                parent_id, name = menus.get(node, (None, ''))
                if name in CONFIG_MENU_NAMES:
                    under_config = True
                    break
                node = parent_id
            if not under_config:
                primary.add(res_model)
    registry._org_primary_models = (key, primary)
    registry._org_parent_fields = None  # parents depend on which models are scoped
    return primary


def _is_candidate(model_cls):
    return not (
        model_cls._abstract
        or model_cls._transient
        or not model_cls._auto
        or model_cls._table_query
        or model_cls._name.startswith(EXCLUDED_PREFIXES)
    )


def _ensure_columns(cr, model_cls, new_fields):
    """Create the columns right away, so the model works before its own
    module is next updated (Odoo then adopts them as usual)."""
    table = model_cls._table
    if not sql.table_exists(cr, table):
        return
    for name, field in new_fields.items():
        if not field.store or sql.column_exists(cr, table, name):
            continue
        comodel_table = field.comodel_name.replace('.', '_')
        sql.create_column(cr, table, name, 'int4')
        sql.add_foreign_key(cr, table, name, comodel_table, 'id', 'restrict')
        sql.create_index(cr, sql.make_index_name(table, name), table, [name])
        _logger.info("Organisation: added %s.%s", model_cls._name, name)


def _inject_org_fields(env, model_cls):
    # Forget what an earlier registry setup decided for this class.
    if model_cls.__dict__.get('_org_dynamic'):
        del model_cls._org_dynamic
        del model_cls._org_scoped

    if not _is_candidate(model_cls) or any(name in model_cls._fields for name in ORG_FIELD_NAMES):
        return
    primary = _primary_models(env)
    if model_cls._name not in primary:
        return
    # A model that _inherits a primary model gets the fields from it.
    if any(parent in primary for parent in model_cls._inherits):
        return

    new_fields = org_scope_fields()
    for name, field in new_fields.items():
        setattr(model_cls, name, field)
        field._toplevel = True
        field.__set_name__(model_cls, name)
        model_cls._fields__[name] = field
    for method in ORG_SCOPE_METHODS:
        setattr(model_cls, method, getattr(OrgScopeMixin, method))
    model_cls._org_scoped = True
    model_cls._org_dynamic = True

    try:
        with env.cr.savepoint():
            _ensure_columns(env.cr, model_cls, new_fields)
    except Exception:
        _logger.exception("Organisation: could not add columns to %s", model_cls._table)


class IrModelFields(models.Model):
    _inherit = 'ir.model.fields'

    def _get_manual_field_data(self, model_name):
        # Called for each model while the registry adds custom fields: the
        # moment to add the Organisation fields to primary models too.
        model_cls = self.pool.get(model_name)
        if model_cls is not None and not model_cls._setup_done__:
            _inject_org_fields(self.env, model_cls)
        return super()._get_manual_field_data(model_name)

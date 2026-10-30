"""Install hooks: taking over the Odoo Mates accounting modules.

Accounting replaces the Odoo Mates accounting suite (om_account_accountant and
the modules it installs). It defines the same models, fields and XML IDs, so
the records those modules hold (assets, budgets, recurring payments, fiscal
years, follow-up plans, financial reports, ...) stay in their tables.

Odoo drops a module's tables when the module is uninstalled, unless another
installed module still owns them. When Accounting is installed on a database
that has the Odoo Mates modules, ``pre_init_hook`` therefore hands everything
they own to Accounting (their external IDs, many2many tables and SQL
constraints) and marks them as uninstalled without running their uninstall:
nothing is dropped, and Odoo no longer loads their code (a model defined by
two modules would otherwise lose the definition of one of them). The views,
menus, actions and access rights of theirs that Accounting does not define
again are removed at the end of the install like any obsolete record of a
module; noupdate data (sequences, mail templates, follow-up plans, rules)
keeps the values the users gave it.

``post_init_hook`` then applies the data upgrades the Odoo Mates modules ship
for the versions installed, and gives the users of the accounting groups the
Accounting permissions matching what they could do before.
"""
import json
import logging

from odoo import api, Command
from odoo.exceptions import UserError
from odoo.tools import parse_version
from odoo.tools.sql import column_exists, create_column

_logger = logging.getLogger(__name__)

MODULE = 'advanced_accounting'

# the modules taken over, in the order their external IDs are claimed: when two
# of them use the same name, the first keeps it
OM_MODULES = (
    'accounting_pdf_reports',
    'om_account_daily_reports',
    'om_account_asset',
    'om_account_budget',
    'om_account_followup',
    'om_fiscal_year',
    'om_recurring_payments',
    'om_account_accountant',
)

VERSIONS_PARAM = 'advanced_accounting.takeover_versions'
SNAPSHOT_TABLE = 'advanced_accounting_takeover_snapshot'
# models whose records the takeover never snapshots: Odoo reflects them itself
UNSNAPSHOT_MODELS = ('ir.model', 'ir.model.fields', 'ir.model.fields.selection', 'ir.model.constraint',
                     'ir.model.relation', 'ir.module.module')


def _installed_om_modules(cr):
    cr.execute("""
        SELECT name, latest_version FROM ir_module_module
         WHERE name IN %s AND state IN ('installed', 'to upgrade', 'to remove')
    """, [OM_MODULES])
    return dict(cr.fetchall())


def _check_dependents(cr, modules):
    """ Refuse the takeover while another installed module needs one of them:
    it would be left without its dependency. """
    cr.execute("""
        SELECT DISTINCT mod.name, dep.name
          FROM ir_module_module_dependency dep
          JOIN ir_module_module mod ON mod.id = dep.module_id
         WHERE dep.name IN %s
           AND mod.name NOT IN %s
           AND mod.state IN ('installed', 'to upgrade')
      ORDER BY mod.name
    """, [tuple(modules), OM_MODULES])
    dependents = cr.fetchall()
    if dependents:
        raise UserError(
            "Accounting replaces the Odoo Mates accounting modules, but these installed modules depend on "
            "them:\n%s\n\nUninstall them first, or change them to depend on advanced_accounting (the models "
            "are the same)." % "\n".join("- %s (needs %s)" % row for row in dependents))


def _claim_xmlids(cr, module_id, om_module):
    """ Move the external IDs of om_module to Accounting. A name Accounting
    already has gets a placeholder name: the record is then removed at the end
    of the install, unless it has another external ID (e.g. the ir.model of a
    core model that several modules extend). """
    cr.execute("""
        UPDATE ir_model_data data SET module = %(new)s
         WHERE data.module = %(old)s
           AND NOT EXISTS (SELECT 1 FROM ir_model_data other
                            WHERE other.module = %(new)s AND other.name = data.name)
    """, {'new': MODULE, 'old': om_module})
    claimed = cr.rowcount
    cr.execute("""
        UPDATE ir_model_data SET module = %(new)s, name = '_om_' || %(old)s || '__' || name
         WHERE module = %(old)s
    """, {'new': MODULE, 'old': om_module})
    _logger.info("Accounting: took over %s external IDs of %s (%s duplicates set aside)",
                 claimed, om_module, cr.rowcount)
    # many2many tables and SQL constraints are owned through ir.model.relation
    # and ir.model.constraint, which name their module directly
    for table in ('ir_model_relation', 'ir_model_constraint'):
        cr.execute(f"""
            DELETE FROM {table} rec
             USING ir_module_module old
             WHERE old.id = rec.module AND old.name = %(old)s
               AND EXISTS (SELECT 1 FROM {table} other WHERE other.module = %(id)s AND other.name = rec.name)
        """, {'old': om_module, 'id': module_id})
        cr.execute(f"""
            UPDATE {table} rec SET module = %(id)s
              FROM ir_module_module old
             WHERE old.id = rec.module AND old.name = %(old)s
        """, {'old': om_module, 'id': module_id})


def _snapshot_noupdate(env):
    """ Keep the noupdate records taken over as they are. Odoo writes the data
    files of a module being installed over every record they name, noupdate or
    not, so the users' changes to them (mail templates, sequences, financial
    reports, rules, ...) would be lost: they are saved here and written back by
    ``_restore_noupdate`` once the data is loaded. """
    cr = env.cr
    cr.execute(f"""
        CREATE TABLE {SNAPSHOT_TABLE} (tbl varchar, res_id int4, data jsonb, relations jsonb)
    """)
    cr.execute("""
        SELECT model, array_agg(res_id) FROM ir_model_data
         WHERE module = %s AND noupdate AND res_id IS NOT NULL AND model NOT IN %s
      GROUP BY model
    """, [MODULE, UNSNAPSHOT_MODELS])
    for model_name, res_ids in cr.fetchall():
        if model_name not in env:
            continue
        Model = env[model_name]
        if Model._abstract or not Model._auto:
            continue
        # the many2many fields stored in a table of their own
        relations = {
            field.relation: (field.column1, field.column2)
            for field in Model._fields.values()
            if field.type == 'many2many' and field.store and field.relation and not field.related
        }
        cr.execute(f"""
            INSERT INTO {SNAPSHOT_TABLE} (tbl, res_id, data)
            SELECT %s, t.id, to_jsonb(t) FROM "{Model._table}" t WHERE t.id = ANY(%s)
        """, [Model._table, res_ids])
        for relation, (column1, column2) in relations.items():
            cr.execute(f"""
                UPDATE {SNAPSHOT_TABLE} snap
                   SET relations = jsonb_set(COALESCE(snap.relations, '{{}}'), ARRAY[%s],
                                             to_jsonb(ARRAY[%s, %s]) || COALESCE((
                       SELECT jsonb_agg(rel."{column2}") FROM "{relation}" rel WHERE rel."{column1}" = snap.res_id
                   ), '[]'::jsonb))
                 WHERE snap.tbl = %s
            """, [relation, column1, column2, Model._table])


def _restore_noupdate(cr):
    cr.execute("SELECT to_regclass(%s)", [SNAPSHOT_TABLE])
    if not cr.fetchone()[0]:
        return
    cr.execute(f"SELECT tbl, res_id, data, relations FROM {SNAPSHOT_TABLE}")
    for table, res_id, data, relations in cr.fetchall():
        cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", [table])
        columns = [col for (col,) in cr.fetchall() if col in data and col not in ('id', 'write_date', 'write_uid')]
        if columns:
            assignments = ", ".join(f'"{col}" = snap."{col}"' for col in columns)
            cr.execute(f"""
                UPDATE "{table}" t SET {assignments}
                  FROM jsonb_populate_record(NULL::"{table}", %s) snap
                 WHERE t.id = %s
            """, [json.dumps(data), res_id])
        for relation, (column1, column2, *targets) in (relations or {}).items():
            cr.execute(f'DELETE FROM "{relation}" WHERE "{column1}" = %s', [res_id])
            for target in targets:
                cr.execute(f"""
                    INSERT INTO "{relation}" ("{column1}", "{column2}") VALUES (%s, %s) ON CONFLICT DO NOTHING
                """, [res_id, target])
    cr.execute(f"DROP TABLE {SNAPSHOT_TABLE}")


def _pre_migrate(cr, versions):
    """ The upgrades of the Odoo Mates modules that must run before the models
    are loaded (their migrations/*/pre-migrate.py). """
    def older(module, version):
        return module in versions and parse_version(versions[module] or '0') < parse_version('19.0.' + version)

    # om_recurring_payments 1.0.1: the currency and journal of recurring payments are stored
    if older('om_recurring_payments', '1.0.1'):
        for table in ('recurring_payment', 'recurring_payment_line'):
            if not column_exists(cr, table, 'currency_id'):
                create_column(cr, table, 'currency_id', 'int4')
                cr.execute(f"""
                    UPDATE {table} rec SET currency_id = company.currency_id
                      FROM res_company company WHERE company.id = rec.company_id
                """)
        if not column_exists(cr, 'recurring_payment', 'journal_id'):
            create_column(cr, 'recurring_payment', 'journal_id', 'int4')
            cr.execute("""
                UPDATE recurring_payment rec SET journal_id = template.journal_id
                  FROM account_recurring_template template WHERE template.id = rec.template_id
            """)

    # om_fiscal_year 1.0.2: the settings wrote the Hard Lock Date for the
    # Tax / Sales / Purchase Lock Dates; copy it into the empty soft locks
    if older('om_fiscal_year', '1.0.2'):
        for field in ('tax_lock_date', 'sale_lock_date', 'purchase_lock_date'):
            if column_exists(cr, 'res_company', field):
                cr.execute(f"""
                    UPDATE res_company SET {field} = hard_lock_date
                     WHERE hard_lock_date IS NOT NULL AND {field} IS NULL
                """)

    # om_account_followup 1.0.4: the company in the subject of the follow-up
    # emails, and the multi-company rules (noupdate records left as they were)
    if older('om_account_followup', '1.0.4'):
        cr.execute("""
            UPDATE mail_template template
               SET subject = (SELECT jsonb_object_agg(term.key, replace(term.value, %(old)s, %(new)s))
                                FROM jsonb_each_text(template.subject) term)
              FROM ir_model_data data
             WHERE data.model = 'mail.template' AND data.module = 'om_account_followup'
               AND data.res_id = template.id AND template.subject::text LIKE %(pattern)s
        """, {'old': '{{ user.company_id.name }}', 'new': '{{ env.company.name }}',
              'pattern': '%{{ user.company_id.name }}%'})
        cr.execute("""
            UPDATE ir_rule rule
               SET domain_force = '[''|'', (''company_id'', ''='', False), (''company_id'', ''in'', company_ids)]'
              FROM ir_model_data data
             WHERE data.model = 'ir.rule' AND data.module = 'om_account_followup'
               AND data.name IN ('om_account_followup_comp_rule', 'om_account_followup_stat_by_partner_comp_rule',
                                 'om_account_followup_stat_comp_rule')
               AND data.res_id = rule.id
               AND regexp_replace(rule.domain_force, '\\s', '', 'g') LIKE '%%(''company_id'',''child_of'',[user.company_id.id])%%'
        """)


def pre_init_hook(env):
    cr = env.cr
    versions = _installed_om_modules(cr)
    if not versions:
        return
    _logger.info("Accounting: taking over the Odoo Mates modules %s", sorted(versions))
    _check_dependents(cr, versions)
    _pre_migrate(cr, versions)

    cr.execute("SELECT id FROM ir_module_module WHERE name = %s", [MODULE])
    module_id = cr.fetchone()[0]
    for om_module in OM_MODULES:
        if om_module in versions:
            _claim_xmlids(cr, module_id, om_module)
    _snapshot_noupdate(env)

    # uninstalled without their uninstall: their tables now belong to Accounting
    cr.execute("""
        UPDATE ir_module_module SET state = 'uninstalled', latest_version = NULL
         WHERE name IN %s
    """, [tuple(versions)])
    # accounting_pdf_reports dropped this table on install: a wizard relation it replaced
    cr.execute("DROP TABLE IF EXISTS account_journal_account_report_partner_ledger_rel")

    cr.execute("""
        INSERT INTO ir_config_parameter (key, value, create_uid, write_uid, create_date, write_date)
        VALUES (%s, %s, 1, 1, now() at time zone 'UTC', now() at time zone 'UTC')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    """, [VERSIONS_PARAM, json.dumps(versions)])


def _post_migrate(env, versions):
    """ The upgrades of the Odoo Mates modules that need the new fields and data
    (their migrations/*/post-migrate.py). """
    def older(module, version):
        return module in versions and parse_version(versions[module] or '0') < parse_version('19.0.' + version)

    # om_recurring_payments 1.1.0: the responsible of a recurring payment
    if older('om_recurring_payments', '1.1.0'):
        env.cr.execute("UPDATE recurring_payment SET user_id = create_uid WHERE user_id IS NULL")

    # om_account_followup 1.1.0: the next actions written on customers become activities
    if older('om_account_followup', '1.1.0'):
        activity_type = env.ref(f'{MODULE}.mail_activity_type_followup', raise_if_not_found=False)
        if activity_type:
            partners = env['res.partner'].with_context(active_test=False).search([
                '|', ('payment_next_action', 'not in', [False, '']), ('payment_next_action_date', '!=', False),
            ])
            today = env.cr.now().date()
            for partner in partners:
                env['mail.activity'].create({
                    'res_model_id': env['ir.model']._get_id('res.partner'),
                    'res_id': partner.id,
                    'activity_type_id': activity_type.id,
                    'summary': 'Payment follow-up',
                    'note': partner.payment_next_action or '',
                    'date_deadline': partner.payment_next_action_date or today,
                    'user_id': (partner.payment_responsible_id or env.ref('base.user_admin')).id,
                })


# what the users of the accounting groups could do in the Odoo Mates modules,
# as Accounting permissions
TAKEOVER_GRANTS = {
    'account.group_account_manager': ['group_accounting_admin'],
    'account.group_account_user': [
        'group_asset_view_all',
        'group_budget_edit_all', 'group_budget_view_all', 'group_budget_delete_all', 'group_budget_approve',
        'group_recurring_edit_all', 'group_recurring_view_all', 'group_recurring_delete_all',
        'group_recurring_confirm',
        'group_closing_edit_all', 'group_closing_view_all', 'group_closing_close',
    ],
    'account.group_account_invoice': ['group_asset_create_only'],
    'account.group_account_readonly': [
        'group_asset_view_all', 'group_budget_view_all', 'group_recurring_view_all', 'group_closing_view_all',
    ],
}


def _grant_permissions(env):
    for source, targets in TAKEOVER_GRANTS.items():
        group = env.ref(source, raise_if_not_found=False)
        users = group.all_user_ids.filtered(lambda u: not u.share) if group else env['res.users']
        if not users:
            continue
        for target in targets:
            env.ref(f'{MODULE}.{target}').write({'user_ids': [Command.link(u.id) for u in users]})


def post_init_hook(env):
    # a plan with three reminders for the companies that have none yet
    env['followup.followup']._create_default_plans(env['res.company'].search([]))

    param = env['ir.config_parameter'].sudo().search([('key', '=', VERSIONS_PARAM)])
    if not param:
        return
    versions = json.loads(param.value)
    param.unlink()
    _restore_noupdate(env.cr)
    env.invalidate_all()
    _post_migrate(env, versions)
    _grant_permissions(env)
    _logger.info("Accounting: took over %s", sorted(versions))

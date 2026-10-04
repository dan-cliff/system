"""
Help Centre — Module Coverage
============================
Tracks which installed Odoo modules have Help Centre articles.

The nightly cron job (``cron_nightly_sync``) does three things each night:

1. **Sync**: Compares ``ir.module.module`` (installed) against this table and
   creates a ``pending`` coverage record for every newly-installed module that
   isn't in the skip list.

2. **Generate**: For every ``pending`` record (that isn't manually skipped)
   it calls the AI service to produce:
       * One overview article covering the whole module.
       * Up to ``_MAX_MODEL_ARTICLES`` articles for the module's principal
         user-facing models (those that appear behind a menu via an act_window
         action).

3. **Commit per module**: Each module is committed individually so a single
   slow or failing AI call never rolls back successfully-generated articles.

All generated articles are created in ``draft`` state so editors can review
and approve them before publishing.
"""

import logging
import re

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skip lists — purely technical modules that don't need user-facing articles
# ---------------------------------------------------------------------------

_SKIP_MODULE_PREFIXES = (
    'auth_', 'base_automation', 'base_import', 'base_setup', 'base_vat',
    'hw_', 'iot_', 'l10n_', 'payment_', 'test_', 'web_',
)

_SKIP_MODULES = frozenset({
    'base', 'bus', 'digest', 'iap', 'link_tracker', 'mail',
    'phone_validation', 'portal', 'rating', 'resource',
    'sms', 'snailmail', 'spreadsheet', 'utm', 'web',
})

# Max per-model articles generated per module
_MAX_MODEL_ARTICLES = 5

# Technical / chatter field names excluded from the AI context prompt
_SKIP_FIELDS = frozenset({
    '__last_update', 'access_token', 'access_url', 'access_warning',
    'activity_date_deadline', 'activity_exception_decoration',
    'activity_exception_icon', 'activity_ids', 'activity_state',
    'activity_summary', 'activity_type_icon', 'activity_type_id',
    'activity_user_id', 'create_date', 'create_uid', 'display_name',
    'id', 'message_attachment_count', 'message_channel_ids',
    'message_follower_ids', 'message_has_error', 'message_has_error_counter',
    'message_has_sms_error', 'message_ids', 'message_is_follower',
    'message_main_attachment_id', 'message_needaction',
    'message_needaction_counter', 'message_partner_ids',
    'message_unread', 'message_unread_counter', 'my_activity_date_deadline',
    'website_message_ids', 'write_date', 'write_uid',
})


def _should_skip_module(module):
    """Return True if this module should not have articles auto-generated."""
    name = module.name
    return name in _SKIP_MODULES or any(name.startswith(p) for p in _SKIP_MODULE_PREFIXES)


class HelpModuleCoverage(models.Model):
    _name = 'help.module.coverage'
    _description = 'Help Centre — Module Coverage'
    _rec_name = 'app_name'
    _order = 'app_name'

    # ── Core fields ────────────────────────────────────────────────────────────

    module_id = fields.Many2one(
        'ir.module.module', 'Module',
        required=True, ondelete='cascade', index=True,
        domain=[('state', '=', 'installed')],
    )
    module_name = fields.Char(
        'Technical Name',
        related='module_id.name', store=True, readonly=True,
    )
    # Use compute (not related) so translate is not inherited from the source
    # translated fields (shortdesc / category name), avoiding the Odoo 19
    # "Translated stored related field" warning that crashes the registry.
    app_name = fields.Char('App Name', compute='_compute_module_labels', store=True, readonly=True)
    module_category = fields.Char('Category', compute='_compute_module_labels', store=True, readonly=True)
    is_app = fields.Boolean(
        'Is App',
        related='module_id.application', store=True, readonly=True,
    )

    # ── Coverage status ────────────────────────────────────────────────────────

    coverage_status = fields.Selection([
        ('pending',    'Pending'),
        ('generating', 'Generating…'),
        ('generated',  'Generated'),
        ('error',      'Error'),
        ('skipped',    'Skipped'),
    ], string='Status', default='pending', required=True, index=True)

    last_generated = fields.Datetime('Last Generated', readonly=True)
    error_message = fields.Text('Last Error', readonly=True)
    skip = fields.Boolean(
        'Skip',
        help='Tick to exclude this module from automatic article generation.',
    )
    active = fields.Boolean(default=True)

    # ── Computed ───────────────────────────────────────────────────────────────

    article_count = fields.Integer(
        'Articles',
        compute='_compute_article_count',
    )

    @api.depends('module_id.shortdesc', 'module_id.category_id.name')
    def _compute_module_labels(self):
        for rec in self:
            rec.app_name = rec.module_id.shortdesc
            rec.module_category = rec.module_id.category_id.name

    def _compute_article_count(self):
        for rec in self:
            rec.article_count = self.env['help.article'].sudo().search_count([
                ('module_ids', 'in', [rec.module_id.id]),
            ])

    # ── Constraints ────────────────────────────────────────────────────────────

    _module_unique = models.Constraint(
        'unique (module_id)',
        'A coverage record already exists for this module.',
    )

    # ── Button actions ─────────────────────────────────────────────────────────

    def action_view_articles(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Articles — %s') % (self.app_name or self.module_name),
            'res_model': 'help.article',
            'view_mode': 'list,form',
            'domain': [('module_ids', 'in', [self.module_id.id])],
            'context': {'default_module_ids': [self.module_id.id]},
        }

    def action_generate(self):
        """Generate (or re-generate) articles for the selected records."""
        count = 0
        for rec in self.filtered(lambda r: not r.skip):
            rec._generate_for_module()
            count += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Help Centre'),
                'message': _(
                    'Generated draft articles for %(n)d module(s). '
                    'Review and publish them from Help Centre → Articles.',
                    n=count,
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_reset_pending(self):
        """Reset status to Pending so the nightly cron will re-generate."""
        self.write({'coverage_status': 'pending', 'error_message': False})

    # ── Class-level helpers ────────────────────────────────────────────────────

    @api.model
    def action_sync_now(self):
        """Server action: sync the coverage table with installed modules."""
        created = self.sync_installed_modules()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Module Coverage Sync'),
                'message': _(
                    '%(n)d new module(s) added to the coverage list.',
                    n=created,
                ),
                'type': 'success' if created else 'info',
                'sticky': False,
            },
        }

    @api.model
    def sync_installed_modules(self):
        """
        Compare installed ``ir.module.module`` records with this coverage table.
        Creates a ``pending`` record for every newly-installed module that
        isn't already tracked and isn't in the technical skip list.

        Returns the number of new records created.
        """
        installed = self.env['ir.module.module'].sudo().search([
            ('state', '=', 'installed'),
        ])
        existing_module_ids = set(
            self.sudo().search([]).mapped('module_id.id')
        )
        created = 0
        for module in installed:
            if module.id in existing_module_ids:
                continue
            if _should_skip_module(module):
                continue
            try:
                self.sudo().create({'module_id': module.id})
                created += 1
            except Exception:
                # Unique constraint violation if run concurrently — ignore
                pass

        if created:
            _logger.info(
                'Help Centre: created %d new module coverage record(s)', created
            )
        return created

    # ── Manual trigger (called from "Generate Missing Articles" button) ──────────

    @api.model
    def run_nightly_sync_now(self):
        """
        Public entry point for the "Generate Missing Articles" button.

        AI article generation is slow (several minutes per module) and would
        exceed the Odoo RPC request timeout if run inline.  Instead this method:
          1. Syncs the module coverage table immediately (fast, DB only).
          2. Triggers the nightly cron to run straight away in a background
             worker — it has no RPC time limit and commits per module.
          3. Returns immediately with the counts so the dialog can show the
             user what was queued.
        """
        if not self.env.user.has_group('help_centre.group_help_centre_manager'):
            raise UserError(_('You must be a Help Centre Manager to run article generation.'))

        new_modules = self.sync_installed_modules()

        max_per_run = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'help_centre.coverage_max_per_run', default='5',
            )
        )

        pending_count = self.sudo().search_count([
            ('coverage_status', '=', 'pending'),
            ('skip', '=', False),
        ])
        queued_count = min(pending_count, max_per_run)

        # Trigger the cron to run immediately in the background
        if queued_count > 0:
            try:
                cron = self.env.ref('help_centre.ir_cron_help_centre_nightly_sync', raise_if_not_found=False)
                if cron:
                    cron.sudo()._trigger()
                    _logger.info(
                        'Help Centre: triggered nightly sync cron — %d module(s) pending',
                        pending_count,
                    )
            except Exception:
                _logger.exception('Help Centre: could not trigger nightly sync cron')

        return {
            'new_modules': new_modules,
            'pending_count': pending_count,
            'queued_count': queued_count,
            'max_per_run': max_per_run,
        }

    # ── Nightly cron ──────────────────────────────────────────────────────────

    @api.model
    def cron_nightly_sync(self):
        """
        Nightly scheduled action:

        1. Sync the coverage table with installed modules.
        2. Process up to ``help_centre.coverage_max_per_run`` (default 5)
           pending modules — generate overview + model articles for each.
        3. Commit after each module so failures are isolated.
        """
        self.sync_installed_modules()

        max_per_run = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'help_centre.coverage_max_per_run', default='5',
            )
        )

        pending = self.sudo().search([
            ('coverage_status', '=', 'pending'),
            ('skip', '=', False),
        ], limit=max_per_run)

        _logger.info(
            'Help Centre nightly sync: %d/%d pending module(s) selected for generation',
            len(pending), max_per_run,
        )

        for rec in pending:
            try:
                rec._generate_for_module()
                self.env.cr.commit()
            except Exception:
                _logger.exception(
                    'Help Centre: article generation failed for module %s',
                    rec.module_name,
                )
                self.env.cr.rollback()

    # ── Core generation ───────────────────────────────────────────────────────

    def _generate_for_module(self):
        """
        Generate draft help articles for this module.

        Produces:
        - One overview article for the whole module.
        - Up to ``_MAX_MODEL_ARTICLES`` articles for the module's main
          user-facing models (those reachable via an act_window menu entry).

        All articles land in ``draft`` state for editor review.
        """
        self.ensure_one()
        self.coverage_status = 'generating'
        module = self.module_id
        ai = self.env['help.ai.service']
        category = self._get_or_create_category(module)
        created = []

        try:
            # 1. Module overview
            overview = self._gen_overview_article(module, category, ai)
            if overview:
                created.append(overview)

            # 2. Per-model articles for principal user-facing models
            for model_rec in self._get_main_models(module)[:_MAX_MODEL_ARTICLES]:
                art = self._gen_model_article(module, model_rec, category, ai)
                if art:
                    created.append(art)

            self.write({
                'coverage_status': 'generated',
                'last_generated': fields.Datetime.now(),
                'error_message': False,
            })
            _logger.info(
                'Help Centre: generated %d article(s) for module %s',
                len(created), module.name,
            )

        except Exception as exc:
            self.write({
                'coverage_status': 'error',
                'error_message': str(exc)[:2000],
            })
            raise

    # ── Article builders ──────────────────────────────────────────────────────

    def _gen_overview_article(self, module, category, ai):
        """Generate one high-level overview article for the whole module."""
        app_name = module.shortdesc or module.name
        topic = (
            f"Complete guide to the '{app_name}' app in Odoo — "
            f"purpose, key features, menu navigation, and step-by-step "
            f"instructions for the most common tasks"
        )

        ctx = []
        if module.summary:
            ctx.append(f"App summary: {module.summary}")
        if module.description:
            clean = re.sub(r'[`*#=\-~^+|<>]+', ' ', module.description)
            clean = ' '.join(clean.split())[:400]
            ctx.append(f"Official description: {clean}")

        main_models = self._get_main_models(module)
        if main_models:
            ctx.append(
                "Key functional areas: " +
                ", ".join(m.name for m in main_models)
            )

        menu_paths = self._get_module_menu_paths(module)
        if menu_paths:
            ctx.append(
                "Menu navigation paths:\n" +
                "\n".join(f"  • {p}" for p in menu_paths[:8])
            )

        content = ai.generate_article(
            topic=topic,
            audience_label='Internal Odoo users (employees and administrators)',
            module_names=module.name,
            style_hint="\n".join(ctx),
        )
        return self._create_article(
            name=f"{app_name} — Overview",
            summary=(
                f"Complete guide to the {app_name} app: "
                f"key features, navigation, and common tasks."
            ),
            content=content,
            module=module,
            category=category,
        )

    def _gen_model_article(self, module, model_rec, category, ai):
        """Generate one article focused on a single user-facing model."""
        app_name = module.shortdesc or module.name
        topic = (
            f"How to work with '{model_rec.name}' in Odoo's {app_name} app — "
            f"creating, viewing, editing, and managing records through the list "
            f"view, form view, and related features"
        )

        ctx = [f"Model: {model_rec.model} ({model_rec.name})"]

        field_summary = self._get_field_summary(model_rec)
        if field_summary:
            ctx.append(f"Available fields: {field_summary}")

        list_cols = self._get_list_view_columns(model_rec.model)
        if list_cols:
            ctx.append(f"List view columns: {', '.join(list_cols)}")

        model_menus = self._get_model_menu_paths(model_rec.model)
        if model_menus:
            ctx.append("Navigate to: " + " / ".join(model_menus[:3]))

        content = ai.generate_article(
            topic=topic,
            audience_label='Internal Odoo users',
            module_names=module.name,
            style_hint="\n".join(ctx),
        )
        return self._create_article(
            name=f"{app_name} — {model_rec.name}",
            summary=(
                f"Step-by-step guide to working with {model_rec.name} "
                f"in the {app_name} app."
            ),
            content=content,
            module=module,
            category=category,
        )

    # ── Creation helper ────────────────────────────────────────────────────────

    def _create_article(self, name, summary, content, module, category):
        """Create a draft (unpublished) ``help.article`` record."""
        return self.env['help.article'].sudo().create({
            'name': name,
            'summary': summary,
            'content': content,
            'state': 'draft',
            'audience': 'internal',
            'category_id': category.id if category else False,
            'module_ids': [(4, module.id)],
            'ai_generated': True,
            'ai_prompt': f'Auto-generated for module: {module.name}',
        })

    # ── Category helper ────────────────────────────────────────────────────────

    def _get_or_create_category(self, module):
        """Return an existing ``help.category`` or create one for the module."""
        # Prefer the Odoo module category name, fall back to app shortdesc
        cat_name = module.category_id.name or module.shortdesc or module.name
        # Strip path prefixes like "Extra Tools / "
        cat_name = cat_name.split('/')[-1].strip() or module.name

        Category = self.env['help.category'].sudo()
        cat = Category.search([('name', '=', cat_name)], limit=1)
        if not cat:
            cat = Category.create({'name': cat_name, 'icon': 'fa-cube'})
        return cat

    # ── Model discovery ────────────────────────────────────────────────────────

    def _get_module_model_records(self, module):
        """
        Return ``ir.model`` records whose model class was *defined* in this
        module.  Uses ``ir.model.data`` for reliable module attribution.
        """
        data_recs = self.env['ir.model.data'].sudo().search([
            ('module', '=', module.name),
            ('model', '=', 'ir.model'),
        ])
        if not data_recs:
            return self.env['ir.model'].sudo().browse([])
        ids = [r.res_id for r in data_recs if r.res_id]
        return self.env['ir.model'].sudo().browse(ids)

    def _get_main_models(self, module):
        """
        Filter module models to those with at least one ``ir.actions.act_window``
        entry — these are the models reachable through menus.
        """
        all_models = self._get_module_model_records(module)
        if not all_models:
            return all_models

        act_model_names = set(
            self.env['ir.actions.act_window'].sudo().search(
                [('res_model', '!=', False)]
            ).mapped('res_model')
        )
        return all_models.filtered(lambda m: m.model in act_model_names)

    # ── Field / view introspection ─────────────────────────────────────────────

    def _get_field_summary(self, model_rec):
        """Build a short human-readable list of a model's user-facing fields."""
        field_recs = self.env['ir.model.fields'].sudo().search([
            ('model_id', '=', model_rec.id),
            ('name', 'not in', list(_SKIP_FIELDS)),
            ('ttype', 'not in', ['binary', 'serialized', 'reference']),
        ], limit=20)
        parts = []
        for f in field_recs:
            part = f"{f.field_description} ({f.ttype})"
            if f.relation:
                part += f" → {f.relation}"
            parts.append(part)
        return "; ".join(parts)

    def _get_list_view_columns(self, model_name):
        """Return field names shown in the model's primary list view."""
        view = self.env['ir.ui.view'].sudo().search([
            ('model', '=', model_name),
            ('type', '=', 'list'),
            ('mode', '=', 'primary'),
        ], limit=1)
        if not view:
            return []
        return re.findall(r'<field[^>]+name="([^"]+)"', view.arch or '')[:8]

    # ── Menu path builders ─────────────────────────────────────────────────────

    def _get_module_menu_paths(self, module):
        """Return menu navigation paths for all act_window actions in a module."""
        module_model_names = list(
            self._get_module_model_records(module).mapped('model')
        )
        if not module_model_names:
            return []
        actions = self.env['ir.actions.act_window'].sudo().search([
            ('res_model', 'in', module_model_names),
        ])
        seen, paths = set(), []
        for action in actions:
            menus = self.env['ir.ui.menu'].sudo().search([
                ('action', '=', f'ir.actions.act_window,{action.id}'),
            ], limit=1)
            for menu in menus:
                path = self._get_menu_path(menu)
                if path not in seen:
                    seen.add(path)
                    paths.append(path)
        return paths

    def _get_model_menu_paths(self, model_name):
        """Return menu paths for a specific model's act_window actions."""
        actions = self.env['ir.actions.act_window'].sudo().search([
            ('res_model', '=', model_name),
        ], limit=5)
        paths = []
        for action in actions:
            menus = self.env['ir.ui.menu'].sudo().search([
                ('action', '=', f'ir.actions.act_window,{action.id}'),
            ], limit=1)
            for menu in menus:
                paths.append(self._get_menu_path(menu))
        return paths

    def _get_menu_path(self, menu):
        """Build a 'Root → Parent → Leaf' navigation path string."""
        parts = []
        cur = menu
        while cur:
            parts.insert(0, cur.name)
            cur = cur.parent_id
        return ' → '.join(parts)

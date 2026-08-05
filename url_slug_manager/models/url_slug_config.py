import re
import logging
from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Slugs already reserved by standard Odoo community + enterprise modules.
# This set is checked on save to prevent silent routing collisions.
RESERVED_ODOO_SLUGS = {
    # --- Odoo Community ---
    'absence-report', 'accounting', 'all_activities', 'all-tasks',
    'all-timesheets', 'analytic-accounts', 'analytic-distribution-models',
    'analytic-items', 'analytic-plans', 'analytic-report', 'attendance-kiosk',
    'attendance-report', 'attendances', 'attendees', 'attribute-categories',
    'attributes', 'automations', 'badges', 'batch-transfers', 'bills',
    'blog-post-pages', 'blogs', 'blog-tag-categories', 'blog-tags', 'boms',
    'burndown-chart', 'calendar', 'certifications', 'combo-choices', 'contacts',
    'course-pages', 'credit-notes', 'crm', 'customer-credit-notes',
    'customer-invoices', 'customer-invoices-analysis', 'customer-payments',
    'customer-products', 'customers', 'dashboards', 'deliveries',
    'delivery-methods', 'departments', 'discount-loyalty', 'discuss',
    'dropships', 'ecommerce-abandoned-carts', 'ecommerce-categories',
    'ecommerce-orders', 'ecommerce-products', 'ecommerce-unpaid-orders',
    'e-learning', 'email-marketing', 'email-templates', 'employees', 'entries',
    'equipement-categories', 'equipement-effectiveness', 'equipments',
    'event-pages', 'events', 'expenses', 'expenses-analysis',
    'expenses-employee', 'expenses-to-process', 'expense-to-approve',
    'field-recycle', 'fiscal-positions', 'fleet', 'forum-close-reasons',
    'forum-post-pages', 'forums', 'forum-tags', 'gift-cards-ewallet',
    'iap-accounts', 'internal', 'inventory', 'invoicing', 'items',
    'job-pages', 'landed-costs', 'livechat', 'lots', 'lunch', 'mail-groups',
    'mailing-lists', 'mail-moderation', 'maintenance', 'maintenance-activity-types',
    'maintenance-calendar', 'maintenance-requests', 'maintenance-requests-analysis',
    'maintenance-stages', 'maintenance-teams', 'manufacturing',
    'manufacturing-products', 'manufacturings', 'moves-analysis', 'moves-history',
    'multi-ledger', 'my-preferences', 'my-tasks', 'my-time-off',
    'online-sales-analysis', 'orders', 'org-chart', 'org-chart-public',
    'payment-methods', 'payment-providers', 'payment-terms', 'payment-tokens',
    'payment-transactions', 'peppol-auth-callback-action', 'physical-inventory',
    'point-of-sale', 'pos-orders', 'pos-sessions', 'pricelists',
    'product-categories', 'production-planning', 'product-pages',
    'product-ribbons', 'products', 'product-tags', 'project',
    'project-activity-plans', 'project-activity-types', 'project-configuration',
    'project-dashboard', 'project_sharing', 'project-stages',
    'project-timesheets', 'purchase', 'purchase-agreements',
    'purchase-analysis', 'purchase-orders', 'purchase-products', 'ranks',
    'receipts', 'reconciliation-models', 'recruitment',
    'recruitment-applications', 'registration-desk', 'repair-orders-analysis',
    'repairs', 'replenishment', 'sales', 'scraps', 'settings', 'sms-marketing',
    'stock-locations', 'stock-report', 'stock-valuation-closing', 'surveys',
    'talent-pool', 'task-ratings', 'tasks', 'tasks-analysis', 'task-stages',
    'task-tags', 'taxes', 'test-model', 'time-off', 'time-off-approval',
    'time-off-overview', 'timesheets', 'timesheets-attendance-analysis',
    'timesheets-billing', 'timesheets-by-employee', 'timesheets-by-project',
    'timesheets-by-task', 'to-do', 'unbuild-orders', 'vendor-bills',
    'vendor-bills-analysis', 'vendor-payments', 'vendor-products',
    'vendor-refunds', 'vendors', 'versions', 'visitors', 'wave-transfers',
    'website', 'website-analytics', 'website-menu', 'website-pages',
    'website-page-views', 'website-rewrite', 'websites', 'workcenter-planning',
    'work-centers', 'workcenters', 'work-entries', 'work-orders',
    'work-orders-analysis', 'zip-prefix',
    # --- Odoo Enterprise ---
    'accounts', 'aged-payable', 'aged-receivable', 'all-tickets',
    'analytic-budgets', 'annual-statements', 'appointment-pages',
    'appointments', 'appraisals', 'approvals', 'articles', 'asset-models',
    'assets', 'automation_webhooks', 'balance-sheet', 'barcode',
    'barcode-batches', 'barcode-mo', 'barcode-operations', 'budget-report',
    'cap-table', 'cap-table-pivot', 'cards', 'cash-flow', 'control-points',
    'customer-batch-payments', 'databases', 'deduplication',
    'deferred-expense', 'deferred-revenue', 'depreciation-schedule',
    'documents', 'documents_portal', 'ecommerce-dashboard', 'ecos',
    'ecos-analysis', 'eco-stages', 'eco-tags', 'eco-types', 'ec-sales-list',
    'employees-planning', 'employee-timesheet', 'equity', 'esg',
    'esg-carbon-analytics', 'esg-carbon-footprint-report', 'esg-csrd',
    'esg-databases', 'esg-emission-factors', 'esg-emission-sources',
    'esg-emitted-emissions', 'esg-employee-commuting', 'esg-gases',
    'esg-gender-parity', 'esg-metrics', 'esg-offset-emissions', 'esg-pay-gap',
    'esg-project-initiatives', 'esg-vsme', 'executive-summary',
    'field-service', 'field-service-map', 'field-service-products',
    'field-service-projects', 'field-service-task-ratings',
    'field-service-tasks', 'field-service-tasks-analysis',
    'field-service-to-schedule', 'field-service-worksheet-templates',
    'financial-budgets', 'fiscal-categories', 'fiscal-report',
    'follow-up-levels', 'frontdesk', 'general-ledger', 'helpdesk',
    'helpdesk-activity-types', 'helpdesk-stages', 'helpdesk-tags',
    'helpdesk-teams', 'intrastat', 'iot', 'journal-report', 'jpk-fa',
    'knowledge', 'loans', 'loans-analysis', 'maintenance-work-centers',
    'maintenance-worksheet-templates', 'marketing-automation', 'meeting-rooms',
    'mps', 'my-planning', 'my-tickets', 'open-shifts', 'partner-ledger',
    'partner-vat-listing', 'payroll', 'payroll-ytd', 'payslips', 'planning',
    'planning-analysis', 'planning-attendance-analysis', 'planning-by-role',
    'planning-materials', 'planning-roles', 'plm', 'production-analysis',
    'profit-and-loss', 'quality', 'quality-alerts', 'quality-alerts-analysis',
    'quality-alert-stages', 'quality-checks', 'quality-checks-analysis',
    'quality-spreadsheet-templates', 'quality-tags', 'quality-teams',
    'quality-worksheet-templates', 'reconcile', 'reconciliation',
    'reconciliation_list', 'reconciliation-report', 'referrals', 'rental',
    'rental-products', 'rental-schedule', 'resource-bookings', 'rooms',
    'schedule-by-project', 'schedule-by-role', 'schedule-by-sales-order',
    'sdd-mandates', 'security-classes', 'shift-templates', 'shop-floor', 'sign',
    'sign-all-documents', 'sign-documents', 'sla-policies',
    'sla-status-analysis', 'social', 'social-campaigns', 'social-posts',
    'staff-bookings', 'stripe-mcc', 'subscriptions', 'tasks-planning-location',
    'tasks-planning-project', 'tasks-planning-user', 'tasks-planning-worksheet',
    'tasks-to-invoice', 'tax-report', 'tax-return', 'ticket-ratings',
    'tickets', 'tickets-analysis', 'timesheets-planning-analysis',
    'transactions', 'transfers', 'trial-balance', 'ubos',
    'unrealized-currency', 'validate-all-timesheets', 'validate-timesheets',
    'valuation-graph', 'valuations', 'vendor-batch-payments', 'whatsapp',
    # --- Odoo framework reserved words ---
    'new', 'action',
}

_SLUG_PATTERN = re.compile(r'^[a-z][a-z0-9_-]*$')


class UrlSlugConfig(models.Model):
    _name = 'url.slug.config'
    _description = 'URL Slug Configuration'
    _order = 'module_display_name, id'
    _rec_name = 'action_name'

    module_name = fields.Char(
        string='Module (Technical)',
        readonly=True,
        required=True,
        help="Internal Odoo module name that owns this action.",
    )
    module_display_name = fields.Char(
        string='Module',
        readonly=True,
        required=True,
        help="Human-readable module name shown in the list.",
    )
    action_id = fields.Many2one(
        'ir.actions.actions',
        string='Action',
        required=True,
        ondelete='cascade',
        domain=[('type', '=', 'ir.actions.act_window')],
    )
    action_name = fields.Char(
        string='Action / View',
        related='action_id.name',
        readonly=True,
        store=False,
    )
    slug = fields.Char(
        string='URL Slug',
        help=(
            "Custom URL path segment for this action.\n"
            "Example: 'physical-assets'  →  /odoo/physical-assets\n\n"
            "Rules:\n"
            "• Lowercase letters, digits, hyphens and underscores only\n"
            "• Must start with a letter\n"
            "• Must not conflict with a reserved Odoo path\n"
            "• Must be unique across all actions\n\n"
            "Leave blank to revert to the default /odoo/action-<id> URL."
        ),
    )
    current_odoo_path = fields.Char(
        string='Current Odoo Path',
        compute='_compute_current_odoo_path',
        help="The path currently stored on the Odoo action record. "
             "Shown for comparison when editing.",
    )
    preview_url = fields.Char(
        string='Preview URL',
        compute='_compute_preview_url',
    )

    _action_unique = models.Constraint(
        'UNIQUE(action_id)',
        'Each action can only have one slug configuration entry.',
    )

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends('action_id')
    def _compute_current_odoo_path(self):
        for rec in self:
            rec.current_odoo_path = rec.action_id.path or ''

    @api.depends('slug')
    def _compute_preview_url(self):
        for rec in self:
            if rec.slug:
                rec.preview_url = f'/odoo/{rec.slug}'
            else:
                rec.preview_url = f'/odoo/action-{rec.action_id.id}' if rec.action_id else ''

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @api.constrains('slug')
    def _check_slug(self):
        for rec in self:
            if not rec.slug:
                continue
            if not _SLUG_PATTERN.match(rec.slug):
                raise ValidationError(
                    f"Invalid slug '{rec.slug}': use only lowercase letters, "
                    f"digits, hyphens and underscores, and start with a letter."
                )
            if rec.slug.startswith(('m-', 'action-')):
                raise ValidationError(
                    f"Slug '{rec.slug}' starts with a reserved prefix "
                    f"('m-' or 'action-'). Please choose a different slug."
                )
            if rec.slug in RESERVED_ODOO_SLUGS:
                raise ValidationError(
                    f"Slug '{rec.slug}' is already reserved by a standard "
                    f"Odoo module. Please choose a different slug."
                )
            # Check uniqueness against other ir.actions.actions records
            # (outside this module's table) that already have this path set.
            conflicting_action = self.env['ir.actions.actions'].sudo().search(
                [('path', '=', rec.slug), ('id', '!=', rec.action_id.id)],
                limit=1,
            )
            if conflicting_action:
                raise ValidationError(
                    f"Slug '{rec.slug}' is already used by action "
                    f"'{conflicting_action.name}' (ID {conflicting_action.id}). "
                    f"Each URL slug must be unique."
                )

    # ------------------------------------------------------------------
    # ORM overrides — sync slug → ir.actions.actions.path
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._apply_slug_to_action()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'slug' in vals:
            for rec in self:
                rec._apply_slug_to_action()
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply_slug_to_action(self):
        """Push the slug value (or False) into ir.actions.actions.path."""
        self.ensure_one()
        if not self.action_id:
            return
        new_path = self.slug.strip() if self.slug else False
        try:
            self.action_id.sudo().write({'path': new_path})
            _logger.info(
                'URL Slug Manager: set path=%r on action %s (%s)',
                new_path, self.action_id.id, self.action_id.name,
            )
        except Exception as exc:
            _logger.warning(
                'URL Slug Manager: failed to set path=%r on action %s: %s',
                new_path, self.action_id.id, exc,
            )
            raise

    def action_find_missing_views(self):
        """
        Button: scan every ir.actions.act_window belonging to a custom module
        (any module whose path lives under /src/user/), create a
        url.slug.config entry for each one that does not yet have one, then
        open the list filtered to 'No Slug Set' so the operator can assign
        slugs to the new records.

        The button carries display="always" in the list view, so it is
        visible whether or not any records are currently selected.
        """
        from odoo.modules.module import get_module_path

        IrModelData = self.env['ir.model.data'].sudo()
        IrModule = self.env['ir.module.module'].sudo()

        # Collect action IDs that already have a slug config record.
        configured_ids = set(self.search([]).mapped('action_id.id'))

        # Walk every ir.model.data row that points to an act_window action.
        all_action_data = IrModelData.search([
            ('model', '=', 'ir.actions.act_window'),
        ])

        # Cache results so we only hit ir.module.module once per module name.
        custom_module_cache = {}   # module_name → bool (is custom?)
        display_name_cache = {}    # module_name → human-readable name

        created = 0

        for data in all_action_data:
            action_id = data.res_id
            module_name = data.module

            # Skip if we already have a config for this action.
            if action_id in configured_ids:
                continue

            # Determine whether this module lives in the custom addons path.
            if module_name not in custom_module_cache:
                try:
                    path = get_module_path(module_name, display_warning=False)
                    custom_module_cache[module_name] = bool(
                        path and '/src/user/' in path
                    )
                except Exception:
                    custom_module_cache[module_name] = False

            if not custom_module_cache[module_name]:
                continue

            # Verify the action still exists in the database.
            action = self.env['ir.actions.act_window'].sudo().browse(action_id)
            if not action.exists():
                continue

            # Resolve the module's human-readable display name.
            if module_name not in display_name_cache:
                mod = IrModule.search([('name', '=', module_name)], limit=1)
                display_name_cache[module_name] = (
                    mod.shortdesc or module_name
                ) if mod else module_name

            self.create({
                'module_name': module_name,
                'module_display_name': display_name_cache[module_name],
                'action_id': action_id,
                'slug': '',
            })
            configured_ids.add(action_id)   # guard against duplicates in loop
            created += 1

        # Load the real action record so the web client receives every field
        # it needs (including the `views` array). A manually constructed dict
        # omits `views`, causing _preprocessAction to blow up with a .map()
        # TypeError on the client side.
        next_action = self.env.ref(
            'url_slug_manager.action_url_slug_config'
        ).sudo().read()[0]
        next_action['context'] = {'search_default_no_slug': 1}

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Find Missing Views',
                'message': (
                    f'{created} new record(s) added.'
                    if created
                    else 'No new views found — everything is already listed.'
                ),
                'type': 'success' if created else 'info',
                'sticky': False,
                'next': next_action,
            },
        }

    def action_rescan_modules(self):
        """
        Button action: re-run the pre-population hook so that any actions
        from newly installed custom modules also receive slug configurations.
        """
        from ..hooks import SLUG_MAPPING
        created = 0
        for xmlid, module_name, module_display_name, slug in SLUG_MAPPING:
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if action is None:
                continue
            existing = self.search([('action_id', '=', action.id)], limit=1)
            if existing:
                continue
            self.create({
                'module_name': module_name,
                'module_display_name': module_display_name,
                'action_id': action.id,
                'slug': slug if not action.path else '',
            })
            created += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Rescan Complete',
                'message': f'{created} new slug configuration(s) added.',
                'type': 'success',
                'sticky': False,
            },
        }

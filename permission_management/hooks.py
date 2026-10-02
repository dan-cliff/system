"""
post_init_hook: populate the Role library from all installed privileges.

Apps from this repository that ship an access_levels.py get their Administrator / Manager /
Employee / View Only roles from _load_access_level_roles instead; ROLE_DEFINITIONS covers
standard Odoo apps and the odd feature group.

Each entry is (privilege_xml_id, group_xml_id, name, description).
If either XML ID is missing (module not installed), the role is skipped
silently — making the library safe on any Odoo instance regardless of
which optional modules are present.
"""

import importlib.util
import logging

from odoo.tools.misc import file_path

from odoo.addons.permission_management import access_levels_lib

_logger = logging.getLogger(__name__)

ROLE_DEFINITIONS = [
    # ── Accounting ────────────────────────────────────────────────────
    (
        'account.res_groups_privilege_accounting',
        'account.group_account_invoice',
        'Accounting – Invoicing',
        'Create and manage customer invoices and vendor bills.',
    ),
    (
        'account.res_groups_privilege_accounting',
        'account.group_account_basic',
        'Accounting – Invoicing & Banks',
        'Full invoicing access plus bank account management.',
    ),
    (
        'account.res_groups_privilege_accounting',
        'account.group_account_manager',
        'Accounting – Administrator',
        'Full accounting administration including configuration and reports.',
    ),
    # ── Accounting Management ─────────────────────────────────────────
    (
        'accounting_management.privilege_accounting_management',
        'accounting_management.group_accounting_admin',
        'Accounting Management – Administrator',
        'Full oversight across Accounting, Sales, Purchase, Inventory and Expenses '
        'via the consolidated Accounting Management hub.',
    ),
    # ── Bank ──────────────────────────────────────────────────────────
    (
        'account.res_group_privilege_accounting_bank',
        'account.group_validate_bank_account',
        'Bank – Validate Bank Account',
        'Permission to validate bank account details.',
    ),
    # ── Canned Responses ──────────────────────────────────────────────
    (
        'mail.res_groups_privilege_canned_response',
        'mail.group_mail_canned_response_admin',
        'Canned Responses – Administrator',
        'Manage shared canned responses for messaging.',
    ),
    # ── Contact ───────────────────────────────────────────────────────
    (
        'base.res_groups_privilege_contact',
        'base.group_partner_manager',
        'Contact – Creation',
        'Create and manage contact records.',
    ),
    # ── Dashboard ─────────────────────────────────────────────────────
    (
        'spreadsheet_dashboard.res_groups_privilege_dashboard',
        'spreadsheet_dashboard.group_dashboard_manager',
        'Dashboard – Admin',
        'Create and manage spreadsheet dashboards.',
    ),
    # ── Digital Signage ───────────────────────────────────────────────
    (
        'digital_signage.privilege_digital_signage',
        'digital_signage.group_signage_marketing',
        'Digital Signage – Marketing',
        'Manage digital signage content and playlists.',
    ),
    (
        'digital_signage.privilege_digital_signage',
        'digital_signage.group_signage_admin',
        'Digital Signage – Administrator',
        'Full administration of digital signage screens and configuration.',
    ),
    # ── Employees ─────────────────────────────────────────────────────
    (
        'hr.res_groups_privilege_employees',
        'hr.group_hr_user',
        'Employees – Officer',
        'Manage all employee records and HR operations.',
    ),
    (
        'hr.res_groups_privilege_employees',
        'hr.group_hr_manager',
        'Employees – Administrator',
        'Full HR administration including configuration and sensitive data.',
    ),
    # ── Expenses ──────────────────────────────────────────────────────
    (
        'hr_expense.res_groups_privilege_expense',
        'hr_expense.group_hr_expense_team_approver',
        'Expenses – Team Approver',
        'Review and approve expense reports submitted by team members.',
    ),
    (
        'hr_expense.res_groups_privilege_expense',
        'hr_expense.group_hr_expense_manager',
        'Expenses – Administrator',
        'Full expenses administration including configuration, all approvals, and reporting.',
    ),
    # ── Export ────────────────────────────────────────────────────────
    (
        'base.res_groups_privilege_export',
        'base.group_allow_export',
        'Export – Allowed',
        'Permission to export data to spreadsheets and CSV files.',
    ),
    # ── Form Builder ──────────────────────────────────────────────────
    (
        'digital_form_builder.privilege_form_builder',
        'digital_form_builder.group_form_builder_user',
        'Form Builder – User',
        'Submit and view digital forms.',
    ),
    (
        'digital_form_builder.privilege_form_builder',
        'digital_form_builder.group_form_builder_manager',
        'Form Builder – Manager',
        'Design forms and manage submissions.',
    ),
    (
        'digital_form_builder.privilege_form_builder',
        'digital_form_builder.group_form_builder_admin',
        'Form Builder – Administrator',
        'Full administration of form builder configuration and templates.',
    ),
    # ── Helpdesk ──────────────────────────────────────────────────────
    (
        'helpdesk.res_groups_privilege_helpdesk',
        'helpdesk.group_helpdesk_user',
        'Helpdesk – User',
        'View and respond to helpdesk tickets.',
    ),
    (
        'helpdesk.res_groups_privilege_helpdesk',
        'helpdesk.group_helpdesk_manager',
        'Helpdesk – Administrator',
        'Full helpdesk administration including team and SLA configuration.',
    ),
    # ── Incident Management ───────────────────────────────────────────
    (
        'incident_management.privilege_incident_report',
        'incident_management.group_incident_confidential_bypass',
        'Incident Management – Confidential Bypass',
        'Access confidential incident records regardless of restriction flags.',
    ),
    (
        'incident_management.privilege_incident_report',
        'emergency_broadcast.group_eb_generate_from_incident',
        'Incident Management – Generate Emergency Broadcast',
        'Generate Emergency Broadcast records directly from an Incident Management report.',
    ),
    # ── Inventory ─────────────────────────────────────────────────────
    (
        'stock.res_groups_privilege_inventory',
        'stock.group_stock_user',
        'Inventory – User',
        'Perform stock operations and view inventory records.',
    ),
    (
        'stock.res_groups_privilege_inventory',
        'stock.group_stock_manager',
        'Inventory – Administrator',
        'Full inventory administration including warehouses and routes.',
    ),
    # ── IoT ───────────────────────────────────────────────────────────
    (
        'iot.res_groups_privilege_iot',
        'iot.group_iot_user',
        'IoT – User',
        'View IoT devices and their status.',
    ),
    (
        'iot.res_groups_privilege_iot',
        'iot.group_iot_admin',
        'IoT – Administrator',
        'Configure and manage IoT devices and boxes.',
    ),
    # ── Manufacturing ─────────────────────────────────────────────────
    (
        'mrp.res_groups_privilege_manufacturing',
        'mrp.group_mrp_user',
        'Manufacturing – User',
        'Process manufacturing orders and work orders.',
    ),
    (
        'mrp.res_groups_privilege_manufacturing',
        'mrp.group_mrp_manager',
        'Manufacturing – Administrator',
        'Full manufacturing administration including BoMs and routing.',
    ),
    # ── Planning ──────────────────────────────────────────────────────
    (
        'planning.res_groups_privilege_planning',
        'planning.group_planning_user',
        'Planning – User',
        'View and confirm allocated planning shifts.',
    ),
    (
        'planning.res_groups_privilege_planning',
        'planning.group_planning_manager',
        'Planning – Administrator',
        'Create and manage all planning schedules and resources.',
    ),
    # ── Point of Sale ─────────────────────────────────────────────────
    (
        'point_of_sale.res_groups_privilege_point_of_sale',
        'point_of_sale.group_pos_user',
        'Point of Sale – User',
        'Operate a point of sale session.',
    ),
    (
        'point_of_sale.res_groups_privilege_point_of_sale',
        'point_of_sale.group_pos_manager',
        'Point of Sale – Administrator',
        'Configure and administer all POS shops and settings.',
    ),
    # ── Products ──────────────────────────────────────────────────────
    (
        'product.res_groups_privilege_product',
        'product.group_product_manager',
        'Products – Create',
        'Create and manage product records.',
    ),
    # ── Project ───────────────────────────────────────────────────────
    (
        'project.res_groups_privilege_project',
        'project.group_project_user',
        'Project – User',
        'Work on assigned project tasks.',
    ),
    (
        'project.res_groups_privilege_project',
        'project.group_project_manager',
        'Project – Administrator',
        'Create and manage all projects and their configuration.',
    ),
    # ── Purchase ──────────────────────────────────────────────────────
    (
        'purchase.res_groups_privilege_purchase',
        'purchase.group_purchase_user',
        'Purchase – User',
        'Create and manage purchase orders.',
    ),
    (
        'purchase.res_groups_privilege_purchase',
        'purchase.group_purchase_manager',
        'Purchase – Administrator',
        'Full purchase administration including vendor pricelists and configuration.',
    ),
    # ── Quality ───────────────────────────────────────────────────────
    (
        'quality.res_groups_privilege_quality',
        'quality.group_quality_user',
        'Quality – User',
        'Perform quality checks and log quality alerts.',
    ),
    (
        'quality.res_groups_privilege_quality',
        'quality.group_quality_manager',
        'Quality – Administrator',
        'Configure quality control points, teams, and reporting.',
    ),
    # ── Reseller Client Manager ───────────────────────────────────────
    (
        'reseller_client_manager.privilege_reseller',
        'reseller_client_manager.group_reseller_user',
        'Reseller – User',
        'View reseller client records.',
    ),
    (
        'reseller_client_manager.privilege_reseller',
        'reseller_client_manager.group_reseller_invoicing',
        'Reseller – Invoicing Integration',
        'Access reseller invoicing and billing integration features.',
    ),
    (
        'reseller_client_manager.privilege_reseller',
        'reseller_client_manager.group_reseller_manager',
        'Reseller – Manager',
        'Manage all reseller client accounts and configuration.',
    ),
    # ── Sales ─────────────────────────────────────────────────────────
    (
        'sales_team.res_groups_privilege_sales',
        'sales_team.group_sale_salesman',
        'Sales – User: Own Documents Only',
        'Create and manage your own sales quotations and orders.',
    ),
    (
        'sales_team.res_groups_privilege_sales',
        'sales_team.group_sale_salesman_all_leads',
        'Sales – User: All Documents',
        'View and manage all sales orders across the team.',
    ),
    (
        'sales_team.res_groups_privilege_sales',
        'sales_team.group_sale_manager',
        'Sales – Administrator',
        'Full sales administration including pricelists, teams, and configuration.',
    ),
    # ── Tour Ticketing & Bookings ─────────────────────────────────────
    (
        'tour_booking.privilege_tour_booking',
        'tour_booking.group_tour_employee',
        'Tour Bookings – Employee',
        'View tour schedules and assigned bookings.',
    ),
    (
        'tour_booking.privilege_tour_booking',
        'tour_booking.group_tour_bookings_officer',
        'Tour Bookings – Bookings Officer',
        'Process and manage tour booking records.',
    ),
    (
        'tour_booking.privilege_tour_booking',
        'tour_booking.group_tour_finance_officer',
        'Tour Bookings – Finance Officer',
        'Access financial reporting and payment records for tour bookings.',
    ),
    (
        'tour_booking.privilege_tour_booking',
        'tour_booking.group_tour_manager',
        'Tour Bookings – Manager',
        'Manage tour products, schedules, and booking teams.',
    ),
    (
        'tour_booking.privilege_tour_booking',
        'tour_booking.group_tour_administrator',
        'Tour Bookings – Administrator',
        'Full tour ticketing administration including configuration and reporting.',
    ),
    # ── Help Centre ───────────────────────────────────────────────────
    (
        'help_centre.privilege_help_centre',
        'help_centre.group_help_centre_editor',
        'Help Centre – Editor',
        'Create, edit, and publish Help Centre articles; use AI article generation.',
    ),
    (
        'help_centre.privilege_help_centre',
        'help_centre.group_help_centre_manager',
        'Help Centre – Manager',
        'Full Help Centre access including chat history, settings, and all editorial capabilities.',
    ),
    # ── Website ───────────────────────────────────────────────────────
    (
        'website.res_groups_privilege_website',
        'website.group_website_restricted_editor',
        'Website – Restricted Editor',
        'Edit website content within restricted areas only.',
    ),
    (
        'website.res_groups_privilege_website',
        'website.group_website_designer',
        'Website – Editor & Designer',
        'Full website editing, design, and theme customisation access.',
    ),
]


def _access_levels_spec(module_name):
    """The module's access_levels.py, loaded from its file (without importing the addon,
    which may not be installed yet), or None when it has none."""
    try:
        path = file_path('%s/access_levels.py' % module_name)
    except (FileNotFoundError, ValueError):
        return None
    spec = importlib.util.spec_from_file_location('%s_access_levels' % module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_access_level_roles(env):
    """Create the Administrator / Manager / Employee / View Only (or custom) roles of every
    installed module that ships an access_levels.py. Roles that already exist (by name) with
    privileges are left alone, empty ones are refilled, and a role is skipped while any of
    its groups is not loaded yet."""
    Role = env['permission.role'].sudo()
    modules = env['ir.module.module'].sudo().search([
        ('state', 'in', ('installed', 'to upgrade', 'to install')),
    ])
    for module in modules:
        spec = _access_levels_spec(module.name)
        if spec is None:
            continue
        if not hasattr(spec, 'MODELS'):
            continue
        for role_name, (description, access) in access_levels_lib.module_roles(spec):
            name = '%s – %s' % (spec.APP_NAME, role_name)
            existing = Role.search([('name', '=', name)], limit=1)
            if existing.line_ids:
                continue
            groups = [
                env.ref(xmlid, raise_if_not_found=False)
                for xmlid in access_levels_lib.role_group_xmlids(module.name, spec, role_name, access)
            ]
            if not groups:
                continue
            if not all(groups):
                _logger.info('Skipping role %s: its groups are not loaded yet.', name)
                continue
            values = {
                'description': description,
                # A role line needs a privilege; the rare group without one is left out.
                'line_ids': [(0, 0, {
                    'privilege_id': group.privilege_id.id,
                    'group_id': group.id,
                }) for group in groups if group.privilege_id],
            }
            if existing:
                # An empty role of the same name (e.g. emptied when its old groups were
                # removed by an upgrade): refill it, keeping its profiles.
                existing.write(values)
            else:
                Role.create(dict(values, name=name))


def post_init_hook(env):
    """Create the predefined Role library, skipping any whose modules are not installed."""
    Role = env['permission.role']

    _load_access_level_roles(env)

    for priv_xml_id, group_xml_id, name, description in ROLE_DEFINITIONS:
        privilege = env.ref(priv_xml_id, raise_if_not_found=False)
        group = env.ref(group_xml_id, raise_if_not_found=False)
        if not privilege or not group:
            continue

        # Idempotent: skip if a role with this exact privilege+group already exists
        already_exists = Role.search([
            ('line_ids.privilege_id', '=', privilege.id),
            ('line_ids.group_id', '=', group.id),
        ], limit=1)
        if already_exists:
            continue

        Role.create({
            'name': name,
            'description': description,
            'line_ids': [(0, 0, {
                'privilege_id': privilege.id,
                'group_id': group.id,
            })],
        })

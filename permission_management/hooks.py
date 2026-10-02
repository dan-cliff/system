"""
post_init_hook: populate the Role library from all installed privileges.

Each entry is (privilege_xml_id, group_xml_id, name, description).
If either XML ID is missing (module not installed), the role is skipped
silently — making the library safe on any Odoo instance regardless of
which optional modules are present.
"""

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
    # ── Asset Management ──────────────────────────────────────────────
    (
        'asset_management.privilege_asset_management',
        'asset_management.group_asset_user',
        'Asset Management – User',
        'View and log asset activity.',
    ),
    (
        'asset_management.privilege_asset_management',
        'asset_management.group_asset_manager',
        'Asset Management – Manager',
        'Create, edit, and manage all asset records.',
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
    # ── Dangerous Goods ───────────────────────────────────────────────
    (
        'dangerous_goods.privilege_dangerous_goods',
        'dangerous_goods.group_dg_user',
        'Dangerous Goods – User',
        'View dangerous goods classifications and documentation.',
    ),
    (
        'dangerous_goods.privilege_dangerous_goods',
        'dangerous_goods.group_dg_manager',
        'Dangerous Goods – Manager',
        'Create and manage dangerous goods records.',
    ),
    (
        'dangerous_goods.privilege_dangerous_goods',
        'dangerous_goods.group_dg_admin',
        'Dangerous Goods – Administrator',
        'Full administration of dangerous goods configuration.',
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
    # ── Employee Healthcare ───────────────────────────────────────────
    (
        'employee_healthcare.privilege_employee_healthcare',
        'employee_healthcare.group_employee_healthcare_employee',
        'Employee Healthcare – Employee',
        'View and edit their own healthcare information.',
    ),
    (
        'employee_healthcare.privilege_employee_healthcare',
        'employee_healthcare.group_employee_healthcare_manager',
        'Employee Healthcare – Manager',
        'View and manage all employee healthcare records, without configuration access.',
    ),
    (
        'employee_healthcare.privilege_employee_healthcare',
        'employee_healthcare.group_employee_healthcare_administrator',
        'Employee Healthcare – Administrator',
        'Full access including lookup table configuration and indicator rule management.',
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
        'incident_management.privilege_incident_management',
        'incident_management.group_incident_user',
        'Incident Management – User',
        'Report and view workplace incidents.',
    ),
    (
        'incident_management.privilege_incident_management',
        'incident_management.group_incident_manager',
        'Incident Management – Manager',
        'Manage incident investigations and corrective actions.',
    ),
    (
        'incident_management.privilege_incident_management',
        'incident_management.group_incident_confidential_bypass',
        'Incident Management – Confidential Bypass',
        'Access confidential incident records regardless of restriction flags.',
    ),
    (
        'incident_management.privilege_incident_management',
        'incident_management.group_incident_admin',
        'Incident Management – Administrator',
        'Full incident management administration and configuration.',
    ),
    (
        'incident_management.privilege_incident_management',
        'emergency_broadcast.group_eb_generate_from_incident',
        'Incident Management – Generate Emergency Broadcast',
        'Generate Emergency Broadcast records directly from an Incident Management report.',
    ),
    # ── Injury Management ─────────────────────────────────────────────
    (
        'injury_management.res_groups_privilege_injury',
        'injury_management.group_injury_user',
        'Injury Management – User',
        'View RTW cases and injury records.',
    ),
    (
        'injury_management.res_groups_privilege_injury',
        'injury_management.group_injury_case_manager',
        'Injury Management – Case Manager',
        'Manage RTW plans, medical appointments, and injury costs.',
    ),
    (
        'injury_management.res_groups_privilege_injury',
        'injury_management.group_injury_admin',
        'Injury Management – Administrator',
        'Full administration of injury management configuration.',
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
    # ── Learning Management System ────────────────────────────────────
    (
        'learning_management.privilege_lms',
        'learning_management.group_lms_employee',
        'LMS – Employee',
        'Enrol in and complete assigned training courses.',
    ),
    (
        'learning_management.privilege_lms',
        'learning_management.group_lms_people_leader',
        'LMS – People Leader',
        'View team training progress and enrolments.',
    ),
    (
        'learning_management.privilege_lms',
        'learning_management.group_lms_facilitator',
        'LMS – Training Facilitator',
        'Deliver training sessions and mark attendance.',
    ),
    (
        'learning_management.privilege_lms',
        'learning_management.group_lms_manager',
        'LMS – Training Manager',
        'Create and manage courses, content, and enrolments.',
    ),
    (
        'learning_management.privilege_lms',
        'learning_management.group_lms_admin',
        'LMS – Administrator',
        'Full LMS administration including configuration and reporting.',
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
    # ── Meeting Management ────────────────────────────────────────────
    (
        'meeting_management.privilege_meeting_management',
        'meeting_management.group_meeting_user',
        'Meeting Management – User',
        'Create and participate in meetings.',
    ),
    (
        'meeting_management.privilege_meeting_management',
        'meeting_management.group_meeting_manager',
        'Meeting Management – Manager',
        'Manage all meetings, agenda templates, and configuration.',
    ),
    # ── Memberships ───────────────────────────────────────────────────
    (
        'membership_management.privilege_membership',
        'membership_management.group_membership_employee',
        'Memberships – Employee',
        'View membership records relevant to your role.',
    ),
    (
        'membership_management.privilege_membership',
        'membership_management.group_membership_manager',
        'Memberships – Manager',
        'Manage member records and renewals.',
    ),
    (
        'membership_management.privilege_membership',
        'membership_management.group_membership_memberships_manager',
        'Memberships – Memberships Manager',
        'Manage membership products and pricing configurations.',
    ),
    (
        'membership_management.privilege_membership',
        'membership_management.group_membership_administrator',
        'Memberships – Administrator',
        'Full administration of membership configuration and reporting.',
    ),
    # ── Permission Management ─────────────────────────────────────────
    (
        'permission_management.privilege_permission_management',
        'permission_management.group_permission_admin',
        'Permission Management – Administrator',
        'Create and manage roles and profiles for all users.',
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
    # ── Report Builder ────────────────────────────────────────────────
    (
        'report_builder.privilege_report_builder',
        'report_builder.group_report_builder_user',
        'Report Builder – User',
        'Run and download existing custom reports.',
    ),
    (
        'report_builder.privilege_report_builder',
        'report_builder.group_report_builder_manager',
        'Report Builder – Manager',
        'Create, configure, and run all custom reports. Full report authoring access.',
    ),
    # ── Print Farm ────────────────────────────────────────────────────
    (
        'print_farm_jobs.privilege_print_farm',
        'print_farm_jobs.group_print_farm_user',
        'Print Farm – User',
        'View and queue jobs in the 3D print farm.',
    ),
    (
        'print_farm_jobs.privilege_print_farm',
        'print_farm_jobs.group_print_farm_manager',
        'Print Farm – Manager',
        'Manage print jobs, assign printers, and track filament.',
    ),
    (
        'print_farm_jobs.privilege_print_farm',
        'print_farm_jobs.group_print_farm_administrator',
        'Print Farm – Administrator',
        'Full print farm administration including printer and filament configuration.',
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
    # ── Technical Configuration ───────────────────────────────────────
    (
        'url_slug_manager.privilege_technical_configuration',
        'url_slug_manager.group_technical_config_admin',
        'Technical Configuration – Administrator',
        'Manage technical configuration such as URL slugs.',
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
    # ── Video Production ──────────────────────────────────────────────
    (
        'video_production.privilege_video_production',
        'video_production.group_video_production_user',
        'Video Production – User',
        'View and contribute to video production projects.',
    ),
    (
        'video_production.privilege_video_production',
        'video_production.group_video_production_manager',
        'Video Production – Manager',
        'Manage all video production projects and resources.',
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
    # ── Workflow Automation ───────────────────────────────────────────
    (
        'workflow_automation.privilege_workflow_automation',
        'workflow_automation.group_workflow_user',
        'Workflow Automation – User',
        'Read-only access to workflows and execution logs.',
    ),
    (
        'workflow_automation.privilege_workflow_automation',
        'workflow_automation.group_workflow_manager',
        'Workflow Automation – Manager',
        'Create, edit and delete workflows, steps and logs.',
    ),
    # ── Zoo Manager ───────────────────────────────────────────────────
    (
        'zoo_manager.res_groups_privilege_zoo_manager',
        'zoo_manager.group_zoo_keeper',
        'Zoo Manager – Keeper',
        'Register and move animals; log feedings, weights and health records.',
    ),
    (
        'zoo_manager.res_groups_privilege_zoo_manager',
        'zoo_manager.group_zoo_manager',
        'Zoo Manager – Administrator',
        'Full zoo administration: species, diets, enclosures and deleting records.',
    ),
]


def post_init_hook(env):
    """Create the predefined Role library, skipping any whose modules are not installed."""
    Role = env['permission.role']

    # Modules that build their own multi-privilege roles
    if 'risk.permission.roles' in env:
        env['risk.permission.roles']._sync_permission_roles()

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

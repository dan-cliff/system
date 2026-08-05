import logging

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-population mapping
# Each entry: (xmlid, module_name, module_display_name, proposed_slug)
#
# Slugs have been verified against the full reserved-path list extracted from
# Odoo 19 community + enterprise source code.  Any action whose xmlid cannot
# be resolved (because the module is not installed) is silently skipped.
# ---------------------------------------------------------------------------
SLUG_MAPPING = [

    # ── Asset Management ────────────────────────────────────────────────────
    ('asset_management.action_asset_asset',
     'asset_management', 'Asset Management', 'physical-assets'),
    ('asset_management.action_asset_defect',
     'asset_management', 'Asset Management', 'asset-defects'),
    ('asset_management.action_asset_maintenance_log',
     'asset_management', 'Asset Management', 'asset-maintenance'),
    ('asset_management.action_asset_usage_log',
     'asset_management', 'Asset Management', 'asset-usage'),
    ('asset_management.action_asset_type',
     'asset_management', 'Asset Management', 'asset-types'),
    ('asset_management.action_asset_subtype',
     'asset_management', 'Asset Management', 'asset-subtypes'),
    ('asset_management.action_asset_defect_severity',
     'asset_management', 'Asset Management', 'asset-defect-severities'),
    ('asset_management.action_asset_maintenance_type',
     'asset_management', 'Asset Management', 'asset-maintenance-types'),
    ('asset_management.action_asset_usage_unit',
     'asset_management', 'Asset Management', 'asset-usage-units'),

    # ── Dangerous Goods ─────────────────────────────────────────────────────
    ('dangerous_goods.action_dg_chemical_all',
     'dangerous_goods', 'Dangerous Goods', 'chemical-register'),
    ('dangerous_goods.action_dg_asbestos_all',
     'dangerous_goods', 'Dangerous Goods', 'asbestos-register'),
    ('dangerous_goods.action_dg_asbestos_inspection_all',
     'dangerous_goods', 'Dangerous Goods', 'asbestos-inspections'),
    ('dangerous_goods.action_dg_chemical_stage',
     'dangerous_goods', 'Dangerous Goods', 'chemical-stages'),
    ('dangerous_goods.action_dg_building',
     'dangerous_goods', 'Dangerous Goods', 'dg-buildings'),
    ('dangerous_goods.action_dg_storage_location',
     'dangerous_goods', 'Dangerous Goods', 'dg-storage-locations'),
    ('dangerous_goods.action_dg_ppe_type',
     'dangerous_goods', 'Dangerous Goods', 'ppe-types'),
    ('dangerous_goods.action_dg_storage_class',
     'dangerous_goods', 'Dangerous Goods', 'dg-storage-classes'),
    ('dangerous_goods.action_dg_adg_class',
     'dangerous_goods', 'Dangerous Goods', 'adg-transport-classes'),
    ('dangerous_goods.action_dg_asbestos_form',
     'dangerous_goods', 'Dangerous Goods', 'asbestos-material-types'),
    ('dangerous_goods.action_dg_control_measure',
     'dangerous_goods', 'Dangerous Goods', 'dg-control-measures'),
    ('dangerous_goods.action_dg_asbestos_remover',
     'dangerous_goods', 'Dangerous Goods', 'asbestos-removalists'),
    ('dangerous_goods.action_ghs_pictogram',
     'dangerous_goods', 'Dangerous Goods', 'ghs-pictograms'),
    ('dangerous_goods.action_ghs_hazard_class',
     'dangerous_goods', 'Dangerous Goods', 'ghs-hazard-classes'),
    ('dangerous_goods.action_ghs_hazard_statement',
     'dangerous_goods', 'Dangerous Goods', 'ghs-hazard-statements'),
    ('dangerous_goods.action_ghs_precautionary_statement',
     'dangerous_goods', 'Dangerous Goods', 'ghs-precautionary-statements'),

    # ── Digital Form Builder ─────────────────────────────────────────────────
    ('digital_form_builder.action_form_template',
     'digital_form_builder', 'Digital Form Builder', 'form-templates'),
    ('digital_form_builder.action_form_template_my_forms',
     'digital_form_builder', 'Digital Form Builder', 'form-library'),
    ('digital_form_builder.action_form_completion',
     'digital_form_builder', 'Digital Form Builder', 'form-submissions'),
    ('digital_form_builder.action_form_schedule',
     'digital_form_builder', 'Digital Form Builder', 'form-schedules'),
    ('digital_form_builder.action_form_group',
     'digital_form_builder', 'Digital Form Builder', 'form-groups'),
    ('digital_form_builder.action_form_template_version',
     'digital_form_builder', 'Digital Form Builder', 'form-versions'),
    ('digital_form_builder.action_lookup_list',
     'digital_form_builder', 'Digital Form Builder', 'form-lookup-lists'),

    # ── Digital Signage ──────────────────────────────────────────────────────
    ('digital_signage.signage_dashboard_action',
     'digital_signage', 'Digital Signage', 'signage-dashboards'),
    ('digital_signage.signage_display_action',
     'digital_signage', 'Digital Signage', 'signage-displays'),
    ('digital_signage.signage_notice_action',
     'digital_signage', 'Digital Signage', 'signage-notices'),

    # ── Employee Healthcare ──────────────────────────────────────────────────
    ('employee_healthcare.action_hr_employee_healthcare',
     'employee_healthcare', 'Employee Healthcare', 'employee-health'),
    ('employee_healthcare.action_healthcare_indicator',
     'employee_healthcare', 'Employee Healthcare', 'health-indicators'),
    ('employee_healthcare.action_healthcare_medication_type',
     'employee_healthcare', 'Employee Healthcare', 'medication-types'),
    ('employee_healthcare.action_healthcare_medication_frequency',
     'employee_healthcare', 'Employee Healthcare', 'medication-frequencies'),
    ('employee_healthcare.action_healthcare_allergy_type',
     'employee_healthcare', 'Employee Healthcare', 'allergy-types'),
    ('employee_healthcare.action_healthcare_allergy_severity',
     'employee_healthcare', 'Employee Healthcare', 'allergy-severities'),
    ('employee_healthcare.action_healthcare_alert_type',
     'employee_healthcare', 'Employee Healthcare', 'health-alert-types'),
    ('employee_healthcare.action_healthcare_alert_severity',
     'employee_healthcare', 'Employee Healthcare', 'health-alert-severities'),
    ('employee_healthcare.action_healthcare_directive_type',
     'employee_healthcare', 'Employee Healthcare', 'healthcare-directive-types'),
    ('employee_healthcare.action_healthcare_insurer',
     'employee_healthcare', 'Employee Healthcare', 'health-insurers'),
    ('employee_healthcare.action_healthcare_ambulance_provider',
     'employee_healthcare', 'Employee Healthcare', 'ambulance-providers'),

    # ── Helpdesk AI ──────────────────────────────────────────────────────────
    # Note: 'helpdesk', 'tickets', 'helpdesk-teams' etc. are reserved by
    # Odoo Enterprise.  These slugs target the extra config models added by
    # this module only.
    ('helpdesk_ai.helpdesk_ticket_category_action',
     'helpdesk_ai', 'Helpdesk AI', 'helpdesk-categories'),
    ('helpdesk_ai.helpdesk_ticket_source_action',
     'helpdesk_ai', 'Helpdesk AI', 'helpdesk-sources'),
    ('helpdesk_ai.helpdesk_sentiment_action',
     'helpdesk_ai', 'Helpdesk AI', 'helpdesk-sentiments'),
    ('helpdesk_ai.helpdesk_primary_target_action',
     'helpdesk_ai', 'Helpdesk AI', 'helpdesk-primary-targets'),
    ('helpdesk_ai.helpdesk_secondary_target_action',
     'helpdesk_ai', 'Helpdesk AI', 'helpdesk-secondary-targets'),
    ('helpdesk_ai.helpdesk_resolution_type_action',
     'helpdesk_ai', 'Helpdesk AI', 'helpdesk-resolution-types'),

    # ── Incident Management ──────────────────────────────────────────────────
    ('incident_management.action_incident_report_all',
     'incident_management', 'Incident Management', 'incidents'),
    ('incident_management.action_incident_report_my',
     'incident_management', 'Incident Management', 'my-incidents'),
    ('incident_management.action_incident_report_pending',
     'incident_management', 'Incident Management', 'incidents-pending'),
    ('incident_management.action_incident_report_investigations',
     'incident_management', 'Incident Management', 'incident-investigations'),
    ('incident_management.action_incident_corrective_action_all',
     'incident_management', 'Incident Management', 'corrective-actions'),
    ('incident_management.action_incident_analysis_by_status',
     'incident_management', 'Incident Management', 'incidents-by-status'),
    ('incident_management.action_incident_analysis_by_severity',
     'incident_management', 'Incident Management', 'incidents-by-severity'),
    ('incident_management.action_incident_analysis_by_category',
     'incident_management', 'Incident Management', 'incidents-by-category'),
    ('incident_management.action_incident_analysis_trend',
     'incident_management', 'Incident Management', 'incident-trends'),
    ('incident_management.action_icam_category',
     'incident_management', 'Incident Management', 'icam-categories'),
    ('incident_management.action_icam_factor',
     'incident_management', 'Incident Management', 'icam-factors'),

    # ── Injury Management ────────────────────────────────────────────────────
    ('injury_management.action_injury_rtw_case_all',
     'injury_management', 'Injury Management', 'rtw-cases'),
    ('injury_management.action_injury_medical_appointment_all',
     'injury_management', 'Injury Management', 'injury-appointments'),
    ('injury_management.action_injury_medical_certificate_all',
     'injury_management', 'Injury Management', 'injury-certificates'),
    ('injury_management.action_injury_rtw_plan_all',
     'injury_management', 'Injury Management', 'rtw-plans'),
    ('injury_management.action_injury_case_note_all',
     'injury_management', 'Injury Management', 'injury-case-notes'),
    ('injury_management.action_injury_cost_all',
     'injury_management', 'Injury Management', 'injury-costs'),
    ('injury_management.action_injury_file_note_all',
     'injury_management', 'Injury Management', 'injury-file-notes'),
    ('injury_management.action_injury_meeting_all',
     'injury_management', 'Injury Management', 'injury-meetings'),
    ('injury_management.action_injury_case_document',
     'injury_management', 'Injury Management', 'injury-case-documents'),

    # ── ISO Compliance ───────────────────────────────────────────────────────
    ('iso_compliance.action_iso_standard_all',
     'iso_compliance', 'ISO Compliance', 'iso-standards'),
    ('iso_compliance.action_iso_standard_review_all',
     'iso_compliance', 'ISO Compliance', 'iso-reviews'),
    ('iso_compliance.action_iso_standard_needs_review',
     'iso_compliance', 'ISO Compliance', 'iso-standards-due-review'),
    ('iso_compliance.action_iso_standard_portal_updates',
     'iso_compliance', 'ISO Compliance', 'iso-portal-updates'),
    ('iso_compliance.action_iso_certification_body',
     'iso_compliance', 'ISO Compliance', 'iso-certification-bodies'),
    ('iso_compliance.action_iso_standard_tag',
     'iso_compliance', 'ISO Compliance', 'iso-tags'),
    ('iso_compliance.action_iso_standard_status',
     'iso_compliance', 'ISO Compliance', 'iso-statuses'),

    # ── Learning Management ──────────────────────────────────────────────────
    # Note: 'e-learning' is reserved by Odoo community.
    ('learning_management.action_lms_course',
     'learning_management', 'Learning Management', 'training-courses'),
    ('learning_management.action_lms_session',
     'learning_management', 'Learning Management', 'training-sessions'),
    ('learning_management.action_lms_enrollment',
     'learning_management', 'Learning Management', 'training-enrollments'),
    ('learning_management.action_lms_enrollment_pending',
     'learning_management', 'Learning Management', 'training-enrollments-pending'),
    ('learning_management.action_lms_employee_record',
     'learning_management', 'Learning Management', 'training-records'),
    ('learning_management.action_lms_assignment',
     'learning_management', 'Learning Management', 'training-assignments'),
    ('learning_management.action_lms_assessment',
     'learning_management', 'Learning Management', 'training-assessments'),
    ('learning_management.action_lms_assessment_template',
     'learning_management', 'Learning Management', 'training-assessment-templates'),
    ('learning_management.action_lms_course_group',
     'learning_management', 'Learning Management', 'training-packages'),
    ('learning_management.action_lms_course_category',
     'learning_management', 'Learning Management', 'training-categories'),
    ('learning_management.action_lms_notification_template',
     'learning_management', 'Learning Management', 'training-notification-templates'),
    ('learning_management.action_lms_notification_log',
     'learning_management', 'Learning Management', 'training-notification-logs'),

    # ── Meeting Management ───────────────────────────────────────────────────
    # Note: 'meeting-rooms' is reserved by Odoo Enterprise.
    ('meeting_management.action_meeting_meeting',
     'meeting_management', 'Meeting Management', 'meeting-minutes'),
    ('meeting_management.action_meeting_template',
     'meeting_management', 'Meeting Management', 'meeting-templates'),
    ('meeting_management.action_meeting_notification_template',
     'meeting_management', 'Meeting Management', 'meeting-notification-templates'),

    # ── Membership Management ────────────────────────────────────────────────
    ('membership_management.action_membership_list',
     'membership_management', 'Membership Management', 'memberships'),
    ('membership_management.action_membership_status',
     'membership_management', 'Membership Management', 'membership-statuses'),
    ('membership_management.action_membership_email_templates',
     'membership_management', 'Membership Management', 'membership-email-templates'),
    ('membership_management.action_membership_letter_templates',
     'membership_management', 'Membership Management', 'membership-letter-templates'),

    # ── Permission Management ────────────────────────────────────────────────
    ('permission_management.action_permission_role',
     'permission_management', 'Permission Management', 'permission-roles'),
    ('permission_management.action_permission_profile',
     'permission_management', 'Permission Management', 'permission-profiles'),

    # ── Print Farm Jobs ──────────────────────────────────────────────────────
    ('print_farm_jobs.action_print_job',
     'print_farm_jobs', 'Print Farm Jobs', 'print-jobs'),
    ('print_farm_jobs.action_print_job_queue',
     'print_farm_jobs', 'Print Farm Jobs', 'print-queue'),
    ('print_farm_jobs.action_print_printer',
     'print_farm_jobs', 'Print Farm Jobs', 'printers'),
    ('print_farm_jobs.action_print_filament',
     'print_farm_jobs', 'Print Farm Jobs', 'filament-catalogue'),
    ('print_farm_jobs.action_print_filament_spool',
     'print_farm_jobs', 'Print Farm Jobs', 'filament-spools'),
    ('print_farm_jobs.action_print_restock_order',
     'print_farm_jobs', 'Print Farm Jobs', 'filament-restock'),

    # ── Reseller Client Manager ──────────────────────────────────────────────
    ('reseller_client_manager.action_client_instance',
     'reseller_client_manager', 'Reseller Client Manager', 'client-instances'),
    ('reseller_client_manager.action_client_server',
     'reseller_client_manager', 'Reseller Client Manager', 'client-servers'),
    ('reseller_client_manager.action_client_plan',
     'reseller_client_manager', 'Reseller Client Manager', 'client-plans'),
    ('reseller_client_manager.action_client_git_repository',
     'reseller_client_manager', 'Reseller Client Manager', 'git-repositories'),
    ('reseller_client_manager.action_client_instance_module',
     'reseller_client_manager', 'Reseller Client Manager', 'client-modules'),
    ('reseller_client_manager.action_client_instance_log',
     'reseller_client_manager', 'Reseller Client Manager', 'client-instance-logs'),
    ('reseller_client_manager.action_client_sync_log',
     'reseller_client_manager', 'Reseller Client Manager', 'client-sync-logs'),

    # ── Soap Recipe Calculator ───────────────────────────────────────────────
    ('soap_recipe_calculator.action_soap_recipe',
     'soap_recipe_calculator', 'Soap Recipe Calculator', 'soap-recipes'),

    # ── Tour Booking ─────────────────────────────────────────────────────────
    ('tour_booking.action_tour_bookings',
     'tour_booking', 'Tour Booking', 'tour-bookings'),
    ('tour_booking.action_tour_slots',
     'tour_booking', 'Tour Booking', 'tour-slots'),
    ('tour_booking.action_tour_checkin_sessions',
     'tour_booking', 'Tour Booking', 'tour-checkins'),
    ('tour_booking.action_tour_holidays',
     'tour_booking', 'Tour Booking', 'tour-holidays'),
    ('tour_booking.action_tour_holiday_types',
     'tour_booking', 'Tour Booking', 'tour-holiday-types'),
    ('tour_booking.action_tour_booking_statuses',
     'tour_booking', 'Tour Booking', 'tour-booking-statuses'),
    ('tour_booking.action_tour_booking_sources',
     'tour_booking', 'Tour Booking', 'tour-booking-sources'),
    ('tour_booking.action_tour_booking_products',
     'tour_booking', 'Tour Booking', 'tour-products'),
    ('tour_booking.action_tour_slot_rules',
     'tour_booking', 'Tour Booking', 'tour-slot-rules'),
    ('tour_booking.action_tour_slot_rule_runs',
     'tour_booking', 'Tour Booking', 'tour-slot-rule-runs'),
    ('tour_booking.action_tour_booking_automations',
     'tour_booking', 'Tour Booking', 'tour-automations'),
    ('tour_booking.action_tour_booking_email_templates',
     'tour_booking', 'Tour Booking', 'tour-email-templates'),
    ('tour_booking.action_tour_booking_letter_templates',
     'tour_booking', 'Tour Booking', 'tour-letter-templates'),

    # ── Video Production ─────────────────────────────────────────────────────
    ('video_production.action_video_production',
     'video_production', 'Video Production', 'video-productions'),
    ('video_production.action_video_production_calendar',
     'video_production', 'Video Production', 'video-production-schedule'),
    ('video_production.action_video_production_publish_calendar',
     'video_production', 'Video Production', 'video-publishing-schedule'),
    ('video_production.action_video_idea',
     'video_production', 'Video Production', 'video-ideas'),
    ('video_production.action_video_shoot',
     'video_production', 'Video Production', 'video-shoots'),
    ('video_production.action_video_shoot_list',
     'video_production', 'Video Production', 'video-shoots-all'),
    ('video_production.action_video_script',
     'video_production', 'Video Production', 'video-scripts'),
    ('video_production.action_video_edit_job',
     'video_production', 'Video Production', 'video-edits'),
    ('video_production.action_video_edit_version',
     'video_production', 'Video Production', 'video-edit-versions'),
    ('video_production.action_video_review',
     'video_production', 'Video Production', 'video-reviews'),
    ('video_production.action_video_metadata',
     'video_production', 'Video Production', 'video-metadata'),
    ('video_production.action_video_platform',
     'video_production', 'Video Production', 'video-platforms'),
    ('video_production.action_video_platform_channel',
     'video_production', 'Video Production', 'video-channels'),
    ('video_production.action_video_platform_playlist',
     'video_production', 'Video Production', 'video-playlists'),
    ('video_production.action_video_production_stage',
     'video_production', 'Video Production', 'video-production-stages'),
    ('video_production.action_video_production_tag',
     'video_production', 'Video Production', 'video-production-tags'),
    ('video_production.action_video_idea_stage',
     'video_production', 'Video Production', 'video-idea-stages'),

    # ── Warehouse Reports ────────────────────────────────────────────────────
    ('warehouse_reports.stock_move_report_action',
     'warehouse_reports', 'Warehouse Reports', 'stock-move-reports'),
    ('warehouse_reports.stock_transfer_report_action',
     'warehouse_reports', 'Warehouse Reports', 'stock-transfer-reports'),
    ('warehouse_reports.stock_product_report_action',
     'warehouse_reports', 'Warehouse Reports', 'stock-product-reports'),
    ('warehouse_reports.stock_valuation_report_action',
     'warehouse_reports', 'Warehouse Reports', 'stock-valuation-reports'),

    # ── Workflow Automation ──────────────────────────────────────────────────
    # Note: 'automations' is reserved by Odoo community.
    ('workflow_automation.action_wf_automation',
     'workflow_automation', 'Workflow Automation', 'workflows'),
    ('workflow_automation.action_wf_execution_log',
     'workflow_automation', 'Workflow Automation', 'workflow-logs'),

    # ── Zyra REST API Manager ────────────────────────────────────────────────
    ('zyra_rest_api_manager.action_api_model_endpoint',
     'zyra_rest_api_manager', 'Zyra REST API Manager', 'api-model-endpoints'),
    ('zyra_rest_api_manager.action_api_custom_endpoint',
     'zyra_rest_api_manager', 'Zyra REST API Manager', 'api-custom-endpoints'),
    ('zyra_rest_api_manager.action_api_app_key',
     'zyra_rest_api_manager', 'Zyra REST API Manager', 'api-keys'),
    ('zyra_rest_api_manager.action_api_auth_endpoint',
     'zyra_rest_api_manager', 'Zyra REST API Manager', 'api-auth-endpoints'),
]


def post_init_hook(env):
    """
    Called once after the module is installed.
    Creates url.slug.config records for every known custom-module action that:
      - exists in the database (module is installed)
      - does not yet have a custom path set on ir.actions.actions
      - does not already have a slug config record
    """
    SlugConfig = env['url.slug.config']
    created = 0
    skipped_existing_path = 0
    skipped_not_found = 0
    skipped_already_configured = 0

    for xmlid, module_name, module_display_name, slug in SLUG_MAPPING:
        action = env.ref(xmlid, raise_if_not_found=False)
        if action is None:
            skipped_not_found += 1
            continue

        # Don't overwrite a path that another mechanism already set
        if action.path:
            skipped_existing_path += 1
            _logger.info(
                'URL Slug Manager: skipping %s — action already has path=%r',
                xmlid, action.path,
            )
            continue

        # Don't create duplicate config records
        existing = SlugConfig.search([('action_id', '=', action.id)], limit=1)
        if existing:
            skipped_already_configured += 1
            continue

        SlugConfig.create({
            'module_name': module_name,
            'module_display_name': module_display_name,
            'action_id': action.id,
            'slug': slug,
        })
        created += 1

    _logger.info(
        'URL Slug Manager post_init_hook: created=%d, '
        'skipped_not_found=%d, skipped_existing_path=%d, '
        'skipped_already_configured=%d',
        created, skipped_not_found, skipped_existing_path,
        skipped_already_configured,
    )

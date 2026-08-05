# -*- coding: utf-8 -*-
import json
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class IncidentReport(models.Model):
    _name = 'incident.report'
    _description = 'Incident Report'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_occurred desc, id desc'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        'Reference', readonly=True, default='New', copy=False, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('assigned', 'Assigned'),
        ('under_investigation', 'Under Investigation'),
        ('corrective_actions', 'Corrective Actions'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False,
        group_expand='_group_expand_states')

    # ── Reporter & Person Involved ─────────────────────────────────────────
    reporter_id = fields.Many2one(
        'res.users', string='Reported By',
        default=lambda self: self.env.user,
        required=True, tracking=True)
    reporter_phone = fields.Char('Reporter Contact Number')
    employee_id = fields.Many2one(
        'hr.employee', string='Employee Involved',
        default=lambda self: self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1))
    department_id = fields.Many2one(
        'hr.department', string='Department',
        compute='_compute_from_employee', store=True, readonly=False)
    job_title = fields.Char(
        'Job Title / Role',
        compute='_compute_from_employee', store=True, readonly=False)
    person_type = fields.Selection([
        ('employee', 'Employee'),
        ('contractor', 'Contractor'),
        ('visitor', 'Visitor'),
        ('member_of_public', 'Member of Public'),
        ('other', 'Other'),
    ], string='Person Type', default='employee', required=True)

    # ── Incident Core ──────────────────────────────────────────────────────
    incident_type_ids = fields.Many2many(
        'incident.type.tag',
        'incident_report_type_rel', 'report_id', 'type_id',
        string='Incident Categories', tracking=True)

    # Computed booleans — used in view invisible/required expressions so that
    # type-specific detail pages show only when the relevant category is selected.
    is_injury = fields.Boolean(compute='_compute_type_booleans', store=True)
    is_illness = fields.Boolean(compute='_compute_type_booleans', store=True)
    is_vehicle = fields.Boolean(compute='_compute_type_booleans', store=True)
    is_plant_equipment = fields.Boolean(compute='_compute_type_booleans', store=True)
    is_drug_alcohol = fields.Boolean(compute='_compute_type_booleans', store=True)
    is_buildings_grounds = fields.Boolean(compute='_compute_type_booleans', store=True)
    is_security = fields.Boolean(compute='_compute_type_booleans', store=True)
    is_theft = fields.Boolean(compute='_compute_type_booleans', store=True)
    is_environmental = fields.Boolean(compute='_compute_type_booleans', store=True)
    is_psychosocial = fields.Boolean(compute='_compute_type_booleans', store=True)
    is_it = fields.Boolean(compute='_compute_type_booleans', store=True)
    is_complaint = fields.Boolean(compute='_compute_type_booleans', store=True)
    is_child_safeguarding = fields.Boolean(compute='_compute_type_booleans', store=True)

    severity = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], string='Severity', default='low', required=True, tracking=True)
    date_occurred = fields.Datetime(
        'Date & Time of Incident', required=True, tracking=True)
    date_reported = fields.Datetime(
        'Date Reported', default=fields.Datetime.now, readonly=True)
    location = fields.Char('Site / Location', required=True)
    exact_location = fields.Char('Exact Location / Area')
    description = fields.Text(
        'Incident Description', required=True,
        help='Describe what happened in as much detail as possible.')
    immediate_action_taken = fields.Text(
        'Immediate Actions Taken',
        help='Describe any steps taken at the time to address the incident.')
    witnesses = fields.Text(
        'Witnesses',
        help='Names and contact details of any witnesses to the incident.')
    near_miss = fields.Boolean(
        'Near Miss', help='Tick if this was a near miss with no actual harm.')

    # ── Assignment ─────────────────────────────────────────────────────────
    responsible_manager_id = fields.Many2one(
        'res.users', string='Responsible Manager',
        domain=[('share', '=', False)], tracking=True)
    date_assigned = fields.Datetime('Date Assigned', readonly=True, copy=False)
    assignment_note = fields.Text('Assignment Note')

    # ── Investigation Summary ──────────────────────────────────────────────
    investigator_ids = fields.Many2many(
        'res.users', 'incident_investigator_rel',
        'incident_id', 'user_id',
        string='Investigators',
        domain=[('share', '=', False)])
    investigation_start = fields.Date('Investigation Start Date')
    investigation_end = fields.Date('Investigation End Date')
    immediate_cause_desc = fields.Text(
        'Immediate Cause',
        help='Describe the direct cause of the incident — the event or condition '
             'that directly resulted in the harm or loss.')
    finding_ids = fields.One2many(
        'incident.icam.finding', 'incident_id', string='ICAM Findings')
    investigation_conclusion = fields.Text('Conclusion')
    investigation_recommendations = fields.Text('Recommendations')

    # ── Corrective Actions ─────────────────────────────────────────────────
    corrective_action_ids = fields.One2many(
        'incident.corrective.action', 'incident_id', string='Corrective Actions')
    corrective_actions_complete = fields.Boolean(
        'All Corrective Actions Complete',
        compute='_compute_corrective_actions_complete', store=True)

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE-SPECIFIC FIELDS — INJURY
    # ═══════════════════════════════════════════════════════════════════════
    injury_body_parts = fields.Char(
        'Body Parts (JSON)',
        default='[]',
        help="JSON array of selected body-part codes from the SVG selector.")
    injury_body_parts_display = fields.Char(
        'Body Parts Affected',
        compute='_compute_body_parts_display', store=True,
        help="Human-readable list of affected body parts.")
    injury_nature = fields.Selection([
        ('laceration', 'Laceration / Cut'),
        ('fracture', 'Fracture / Break'),
        ('burn', 'Burn / Scald'),
        ('sprain_strain', 'Sprain / Strain'),
        ('contusion', 'Contusion / Bruising'),
        ('amputation', 'Amputation'),
        ('crush', 'Crush Injury'),
        ('eye_injury', 'Eye Injury'),
        ('head_injury', 'Head Injury'),
        ('electric_shock', 'Electric Shock'),
        ('other', 'Other'),
    ], string='Nature of Injury')
    injury_mechanism = fields.Selection([
        ('fall_same_level', 'Fall — Same Level'),
        ('fall_from_height', 'Fall — From Height'),
        ('struck_by_object', 'Struck by Object'),
        ('struck_against', 'Struck Against Object'),
        ('caught_in_between', 'Caught In / Between'),
        ('overexertion', 'Overexertion / Manual Handling'),
        ('repetitive_motion', 'Repetitive Motion'),
        ('exposure_substance', 'Exposure to Substance'),
        ('exposure_temperature', 'Exposure to Extreme Temperature'),
        ('vehicle_related', 'Vehicle Related'),
        ('other', 'Other'),
    ], string='Mechanism of Injury')
    injury_treatment = fields.Selection([
        ('none', 'No Treatment Required'),
        ('first_aid', 'First Aid Only'),
        ('medical_treatment', 'Medical Treatment'),
        ('hospitalisation', 'Hospitalisation'),
    ], string='Treatment Received')
    injury_lost_time = fields.Boolean(
        'Lost Time Injury (LTI)',
        help='Tick if the injured person was unable to work on the next scheduled shift.')
    injury_days_lost = fields.Integer('Days Lost')
    injury_return_date = fields.Date('Actual / Estimated Return-to-Work Date')
    injury_restricted_duties = fields.Boolean('Restricted / Modified Duties')
    injury_medical_officer = fields.Text('Treating Medical Officer / Facility')
    injury_notifiable = fields.Boolean(
        'Notifiable Incident',
        help='Check if this incident must be reported to the relevant regulator.')
    injury_regulator_notified = fields.Boolean('Regulator Notified')
    injury_notification_date = fields.Date('Regulator Notification Date')
    injury_additional_notes = fields.Text('Additional Notes')

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE-SPECIFIC FIELDS — ILLNESS
    # ═══════════════════════════════════════════════════════════════════════
    illness_type = fields.Selection([
        ('respiratory', 'Respiratory'),
        ('skin_dermatological', 'Skin / Dermatological'),
        ('musculoskeletal', 'Musculoskeletal'),
        ('noise_induced_hl', 'Noise Induced Hearing Loss'),
        ('stress_mental_health', 'Stress / Mental Health'),
        ('gastrointestinal', 'Gastrointestinal'),
        ('cardiovascular', 'Cardiovascular'),
        ('infectious', 'Infectious Disease'),
        ('other', 'Other'),
    ], string='Type of Illness')
    illness_symptoms = fields.Text('Symptoms Described')
    illness_onset_date = fields.Date('Date of Onset / First Symptom')
    illness_exposure_type = fields.Char('Type of Exposure / Hazard')
    illness_exposure_duration = fields.Char('Duration of Exposure')
    illness_treatment = fields.Selection([
        ('none', 'No Treatment Required'),
        ('first_aid', 'First Aid Only'),
        ('medical_treatment', 'Medical Treatment'),
        ('hospitalisation', 'Hospitalisation'),
    ], string='Illness Treatment Received')
    illness_lost_time = fields.Boolean('Lost Time Due to Illness')
    illness_days_lost = fields.Integer('Illness Days Lost')
    illness_return_date = fields.Date('Illness — Estimated Return-to-Work Date')
    illness_workers_comp = fields.Boolean("Workers' Compensation Claim")
    illness_additional_notes = fields.Text('Illness — Additional Notes')

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE-SPECIFIC FIELDS — VEHICLE
    # ═══════════════════════════════════════════════════════════════════════
    vehicle_registration = fields.Char('Vehicle Registration')
    vehicle_type = fields.Selection([
        ('light_vehicle', 'Light Vehicle (Car / Ute / Van)'),
        ('heavy_vehicle', 'Heavy Vehicle / Truck'),
        ('forklift', 'Forklift'),
        ('mobile_plant', 'Mobile Plant'),
        ('motorcycle', 'Motorcycle / ATV'),
        ('other', 'Other'),
    ], string='Vehicle Type')
    vehicle_make_model = fields.Char('Make / Model')
    vehicle_ownership = fields.Selection([
        ('company', 'Company Vehicle'),
        ('personal', 'Personal Vehicle'),
        ('hire', 'Hire / Rental Vehicle'),
        ('third_party', 'Third Party Vehicle'),
    ], string='Vehicle Ownership')
    vehicle_driver_name = fields.Char('Driver Name')
    vehicle_driver_licence = fields.Char('Driver Licence Number')
    vehicle_estimated_speed = fields.Integer('Estimated Speed at Time of Incident (km/h)')
    vehicle_road_conditions = fields.Selection([
        ('dry', 'Dry / Sealed'),
        ('wet', 'Wet / Slippery'),
        ('gravel', 'Gravel / Unsealed'),
        ('icy', 'Icy / Frosted'),
        ('off_road', 'Off Road'),
        ('other', 'Other'),
    ], string='Road / Surface Conditions')
    vehicle_police_reported = fields.Boolean('Reported to Police')
    vehicle_police_report_no = fields.Char('Police Event / Report Number')
    vehicle_third_party = fields.Boolean('Third Party Involved')
    vehicle_third_party_details = fields.Text('Third Party Details (name, registration, insurer)')
    vehicle_damage_description = fields.Text('Vehicle / Property Damage Description')
    vehicle_towed = fields.Boolean('Vehicle Required Towing')
    vehicle_additional_notes = fields.Text('Vehicle — Additional Notes')

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE-SPECIFIC FIELDS — PLANT AND EQUIPMENT
    # ═══════════════════════════════════════════════════════════════════════
    plant_equipment_name = fields.Char('Equipment Name / Description')
    plant_equipment_tag = fields.Char('Equipment ID / Asset Tag Number')
    plant_equipment_type = fields.Selection([
        ('fixed_plant', 'Fixed Plant / Machinery'),
        ('mobile_plant', 'Mobile Plant'),
        ('hand_power_tool', 'Hand Tool / Power Tool'),
        ('lifting_equipment', 'Lifting Equipment / Crane'),
        ('pressure_vessel', 'Pressure Vessel / Pipework'),
        ('electrical_equipment', 'Electrical Equipment'),
        ('hvac', 'HVAC / Mechanical Services'),
        ('other', 'Other'),
    ], string='Equipment Type')
    plant_operator_name = fields.Char('Operator / User at Time of Incident')
    plant_failure_type = fields.Selection([
        ('mechanical', 'Mechanical Failure'),
        ('electrical', 'Electrical Failure'),
        ('structural', 'Structural Failure'),
        ('software_control', 'Software / Control Failure'),
        ('operator_error', 'Operator Error'),
        ('maintenance_related', 'Maintenance Related'),
        ('design_defect', 'Design / Manufacturing Defect'),
        ('other', 'Other'),
    ], string='Failure / Incident Type')
    plant_last_maintenance_date = fields.Date('Date of Last Scheduled Maintenance')
    plant_current_certification = fields.Boolean('Current Inspection Certificate / Registration')
    plant_taken_out_of_service = fields.Boolean('Equipment Taken Out of Service')
    plant_damage_description = fields.Text('Damage / Fault Description')
    plant_additional_notes = fields.Text('Plant & Equipment — Additional Notes')

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE-SPECIFIC FIELDS — DRUG AND ALCOHOL
    # ═══════════════════════════════════════════════════════════════════════
    da_persons_involved = fields.Text('Person(s) Involved')
    da_substance_suspected = fields.Char('Substance Suspected')
    da_observed_behaviour = fields.Text('Observed Behaviour / Indicators')
    da_test_conducted = fields.Boolean('Workplace Test Conducted')
    da_test_type = fields.Selection([
        ('breathalyser', 'Breathalyser'),
        ('urine', 'Urine Analysis'),
        ('blood', 'Blood Test'),
        ('saliva_oral', 'Oral Fluid / Saliva'),
        ('other', 'Other'),
    ], string='Type of Test')
    da_test_result = fields.Selection([
        ('negative', 'Negative'),
        ('positive', 'Positive'),
        ('refused', 'Test Refused'),
        ('pending', 'Result Pending'),
    ], string='Test Result')
    da_testing_officer = fields.Char('Testing Officer / Authorised Agency')
    da_stood_down = fields.Boolean('Employee Stood Down / Removed from Duty')
    da_referred_eap = fields.Boolean('Referred to EAP / Support Services')
    da_disciplinary = fields.Boolean('Disciplinary Process Initiated')
    da_additional_notes = fields.Text('Drug & Alcohol — Additional Notes')

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE-SPECIFIC FIELDS — BUILDINGS AND GROUNDS
    # ═══════════════════════════════════════════════════════════════════════
    bg_building = fields.Char('Building / Structure')
    bg_area = fields.Char('Specific Area / Zone')
    bg_damage_type = fields.Selection([
        ('structural', 'Structural Damage'),
        ('roof_ceiling', 'Roof / Ceiling'),
        ('electrical_services', 'Electrical Services'),
        ('plumbing_hydraulic', 'Plumbing / Hydraulic'),
        ('fire_systems', 'Fire Systems / Suppression'),
        ('fixtures_fittings', 'Fixtures & Fittings'),
        ('grounds_landscaping', 'Grounds / Landscaping'),
        ('fencing_perimeter', 'Fencing / Perimeter'),
        ('other', 'Other'),
    ], string='Damage / Incident Type')
    bg_damage_cause = fields.Char('Cause of Damage / Incident')
    bg_estimated_cost = fields.Float('Estimated Cost of Damage ($)', digits=(10, 2))
    bg_temporary_measures = fields.Text('Temporary / Interim Measures Taken')
    bg_area_isolated = fields.Boolean('Area Isolated / Barricaded')
    bg_repairs_required = fields.Boolean('Repairs Required')
    bg_repair_description = fields.Text('Repairs Required — Description')
    bg_insurance_claim = fields.Boolean('Insurance Claim Required')
    bg_additional_notes = fields.Text('Buildings & Grounds — Additional Notes')

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE-SPECIFIC FIELDS — SECURITY
    # ═══════════════════════════════════════════════════════════════════════
    security_breach_type = fields.Selection([
        ('unauthorised_access', 'Unauthorised Access'),
        ('vandalism', 'Vandalism / Malicious Damage'),
        ('assault', 'Assault / Physical Attack'),
        ('threat_intimidation', 'Threat / Intimidation'),
        ('suspicious_activity', 'Suspicious Activity'),
        ('cyber_it', 'Cyber / IT Security Breach'),
        ('other', 'Other'),
    ], string='Type of Security Incident')
    security_area = fields.Char('Area / Zone Where Incident Occurred')
    security_police_notified = fields.Boolean('Police Notified')
    security_police_report_no = fields.Char('Security — Police Report Number')
    security_footage_available = fields.Boolean('CCTV / Security Footage Available')
    security_footage_preserved = fields.Boolean('Footage Preserved / Downloaded')
    security_persons_involved = fields.Text('Description of Persons Involved')
    security_response_taken = fields.Text('Security Response Actions Taken')
    security_access_revoked = fields.Boolean('Access Rights Revoked / Changed')
    security_additional_notes = fields.Text('Security — Additional Notes')

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE-SPECIFIC FIELDS — THEFT
    # ═══════════════════════════════════════════════════════════════════════
    theft_items_description = fields.Text('Description of Items Stolen / Missing')
    theft_estimated_value = fields.Float('Estimated Value of Items ($)', digits=(10, 2))
    theft_location = fields.Char('Location Where Theft Occurred')
    theft_police_notified = fields.Boolean('Theft — Police Notified')
    theft_police_report_no = fields.Char('Theft — Police Report Number')
    theft_cctv_available = fields.Boolean('Theft — CCTV Available')
    theft_cctv_preserved = fields.Boolean('Theft — Footage Preserved')
    theft_suspect_details = fields.Text('Suspect Details (if known)')
    theft_insurance_claim = fields.Boolean('Theft — Insurance Claim Required')
    theft_additional_notes = fields.Text('Theft — Additional Notes')

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE-SPECIFIC FIELDS — ENVIRONMENTAL
    # ═══════════════════════════════════════════════════════════════════════
    env_media_affected = fields.Selection([
        ('air', 'Air / Atmosphere'),
        ('surface_water', 'Surface Water'),
        ('groundwater', 'Groundwater'),
        ('soil_land', 'Soil / Land'),
        ('noise_vibration', 'Noise / Vibration'),
        ('multiple', 'Multiple Media'),
        ('other', 'Other'),
    ], string='Environmental Media Affected')
    env_substance = fields.Char('Substance / Pollutant Released')
    env_quantity_released = fields.Char('Estimated Quantity Released')
    env_containment_taken = fields.Boolean('Containment Measures Taken')
    env_containment_description = fields.Text('Containment / Response Actions Description')
    env_regulatory_required = fields.Boolean('Regulatory Notification Required')
    env_regulatory_body = fields.Char('Relevant Regulatory Body / Authority')
    env_notified = fields.Boolean('Regulatory Body Notified')
    env_notification_date = fields.Date('Date Notified to Regulator')
    env_cleanup_required = fields.Boolean('Cleanup / Remediation Required')
    env_cleanup_description = fields.Text('Cleanup / Remediation Plan Description')
    env_additional_notes = fields.Text('Environmental — Additional Notes')

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE-SPECIFIC FIELDS — PSYCHOSOCIAL
    # ═══════════════════════════════════════════════════════════════════════
    ps_incident_type = fields.Selection([
        ('bullying', 'Workplace Bullying'),
        ('harassment', 'Harassment'),
        ('sexual_harassment', 'Sexual Harassment'),
        ('aggression_coworker', 'Aggression / Violence — Co-worker'),
        ('aggression_client', 'Aggression / Violence — Client / Customer'),
        ('work_stress', 'Work-related Stress / Burnout'),
        ('traumatic_event', 'Traumatic Event / Critical Incident'),
        ('discrimination', 'Discrimination'),
        ('vicarious_trauma', 'Vicarious Trauma'),
        ('other', 'Other'),
    ], string='Nature of Psychosocial Incident')
    ps_relationship = fields.Selection([
        ('colleague', 'Colleague (same level)'),
        ('supervisor', 'Supervisor / Manager'),
        ('subordinate', 'Subordinate / Direct Report'),
        ('client_customer', 'Client / Customer'),
        ('member_of_public', 'Member of Public'),
        ('other', 'Other'),
    ], string='Relationship of Subject to Reporter')
    ps_duration = fields.Selection([
        ('single', 'Single / Isolated Incident'),
        ('weeks', 'Recurring over Weeks'),
        ('months', 'Recurring over Months'),
        ('long_term', 'Ongoing — Long Term'),
    ], string='Duration / Frequency')
    ps_persons_involved = fields.Text(
        'Psychosocial — Person(s) Involved',
        help='Names and roles/positions of person(s) involved. '
             'This field is confidential — handle with care.')
    ps_impact_on_work = fields.Text(
        'Impact on Work / Wellbeing',
        help='Describe the impact on the affected person\'s work performance, '
             'attendance, or general wellbeing.')
    ps_prior_reports = fields.Boolean(
        'Previous Reports / Incidents',
        help='Has this person reported similar incidents previously?')
    ps_prior_reports_details = fields.Text(
        'Previous Report Details',
        help='Provide any known details of prior reports or incidents.')
    ps_witness_details = fields.Text(
        'Witness / Bystander Details',
        help='Names and contact details of any witnesses or bystanders.')
    ps_support_offered = fields.Selection([
        ('none', 'No Immediate Support Required'),
        ('manager_discussion', 'Manager Discussion / Debrief'),
        ('eap_referral', 'EAP Referral'),
        ('medical_referral', 'Medical / GP Referral'),
        ('formal_investigation', 'Formal Investigation Initiated'),
    ], string='Support / Action Offered')
    ps_eap_referral = fields.Boolean('EAP Referral Accepted')
    ps_hr_notified = fields.Boolean('HR Notified')
    ps_formal_complaint = fields.Boolean('Formal Complaint Lodged')
    ps_formal_complaint_ref = fields.Char(
        'Formal Complaint Reference No.',
        help='Reference number assigned to any formal complaint or investigation.')
    ps_additional_notes = fields.Text('Psychosocial — Additional Notes')

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE-SPECIFIC FIELDS — INFORMATION TECHNOLOGY
    # ═══════════════════════════════════════════════════════════════════════
    it_incident_category = fields.Selection([
        ('hardware_failure',    'Hardware Failure'),
        ('software_error',      'Software Error / Bug'),
        ('network_outage',      'Network / Connectivity Outage'),
        ('data_breach',         'Data Breach'),
        ('cybersecurity',       'Cybersecurity Attack'),
        ('unauthorised_access', 'Unauthorised Access'),
        ('data_loss',           'Data Loss'),
        ('service_disruption',  'Service Disruption'),
        ('other',               'Other'),
    ], string='IT Incident Category')
    it_systems_affected = fields.Text('Systems / Applications Affected')
    it_data_involved = fields.Boolean('Personal / Sensitive Data Involved')
    it_data_description = fields.Text('Description of Data Involved')
    it_regulatory_notification = fields.Boolean('IT — Regulatory Notification Required',
        help='e.g. Notifiable Data Breach under the Privacy Act')
    it_ticket_number = fields.Char('IT Support Ticket Number', size=64)
    it_department_notified = fields.Boolean('IT Department Notified')
    it_department_notified_date = fields.Datetime('Date / Time IT Notified')
    it_additional_notes = fields.Text('IT — Additional Notes')

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE-SPECIFIC FIELDS — COMPLAINT
    # ═══════════════════════════════════════════════════════════════════════
    cmp_complaint_type = fields.Selection([
        ('service_quality',  'Service Quality'),
        ('staff_behaviour',  'Staff Behaviour'),
        ('policy_grievance', 'Policy / Procedure Grievance'),
        ('discrimination',   'Discrimination'),
        ('harassment',       'Harassment'),
        ('billing_dispute',  'Billing / Financial Dispute'),
        ('privacy_breach',   'Privacy Breach'),
        ('facilities',       'Facilities / Environment'),
        ('other',            'Other'),
    ], string='Complaint Type')
    cmp_received_by = fields.Char('Received By', size=128)
    cmp_received_date = fields.Date('Date Complaint Received')
    cmp_subject = fields.Text('Subject of Complaint')
    cmp_resolution_sought = fields.Text('Resolution Sought by Complainant')
    cmp_formal_complaint = fields.Boolean('Complaint — Formal Complaint Lodged')
    cmp_formal_ref = fields.Char('Formal Complaint Reference', size=64)
    cmp_escalated = fields.Boolean('Escalated to Management')
    cmp_outcome = fields.Text('Outcome / Resolution')
    cmp_additional_notes = fields.Text('Complaint — Additional Notes')

    # ═══════════════════════════════════════════════════════════════════════
    # TYPE-SPECIFIC FIELDS — CHILD SAFEGUARDING
    # ═══════════════════════════════════════════════════════════════════════
    cs_concern_type = fields.Selection([
        ('physical_abuse',            'Physical Abuse'),
        ('emotional_abuse',           'Emotional Abuse'),
        ('sexual_abuse',              'Sexual Abuse'),
        ('neglect',                   'Neglect'),
        ('bullying',                  'Bullying / Peer Abuse'),
        ('grooming',                  'Grooming'),
        ('online_safety',             'Online Safety Concern'),
        ('inappropriate_relationship','Inappropriate Relationship'),
        ('other',                     'Other'),
    ], string='Nature of Concern')
    cs_child_identifier = fields.Char('Child Reference / Identifier', size=64,
        help='Use a reference code or identifier — do not record the child\'s full name here.')
    cs_child_age_range = fields.Selection([
        ('under_5',  'Under 5'),
        ('5_to_9',   '5 – 9'),
        ('10_to_12', '10 – 12'),
        ('13_to_15', '13 – 15'),
        ('16_to_17', '16 – 17'),
        ('unknown',  'Unknown'),
    ], string='Child Age Range')
    cs_persons_of_concern = fields.Text('Person(s) of Concern')
    cs_mandatory_report_required = fields.Boolean('Mandatory Report Required')
    cs_mandatory_report_date = fields.Date('Mandatory Report Date')
    cs_mandatory_report_ref = fields.Char('Mandatory Report Reference', size=64)
    cs_cpo_notified = fields.Boolean('Child Protection Officer Notified')
    cs_cpo_name = fields.Char('Child Protection Officer Name', size=128)
    cs_external_agency_notified = fields.Boolean('External Agency Notified',
        help='e.g. Police, DHHS, Child Protection Services')
    cs_external_agency_name = fields.Char('External Agency / Department', size=128)
    cs_external_ref = fields.Char('External Reference Number', size=64)
    cs_support_provided = fields.Text('Support Provided to Child')
    cs_additional_notes = fields.Text('Child Safeguarding — Additional Notes')

    # ── Confidentiality ────────────────────────────────────────────────────
    is_confidential = fields.Boolean(
        'Confidential', default=False, tracking=True,
        help='When enabled, only users listed in the Authorised Users list '
             '(plus the reporter, responsible manager, and anyone with the '
             'Confidential Bypass permission) can view this record.')
    confidential_user_ids = fields.Many2many(
        'res.users',
        'incident_confidential_user_rel',
        'incident_id', 'user_id',
        string='Authorised Users',
        domain=[('share', '=', False)],
        help='Internal users who may view this confidential incident report.')
    confidential_user_count = fields.Integer(
        'Authorised User Count', compute='_compute_confidential_user_count')

    # ── Computed / Smart Buttons ───────────────────────────────────────────
    attachment_count = fields.Integer(
        'Attachments', compute='_compute_attachment_count')
    corrective_action_count = fields.Integer(
        'Corrective Action Count', compute='_compute_counts', store=True)
    finding_count = fields.Integer(
        'ICAM Finding Count', compute='_compute_counts', store=True)

    # ── Body-part display names (kept in sync with body_part_widget SVG codes) ──
    BODY_PART_NAMES = {
        # ── Main body — front ─────────────────────────────────────────────
        'head':           'Head',
        'neck':           'Neck',
        'left_shoulder':  'Left Shoulder',
        'left_arm':       'Left Arm',
        'left_elbow':     'Left Elbow',
        'left_hand':      'Left Hand',
        'right_shoulder': 'Right Shoulder',
        'right_arm':      'Right Arm',
        'right_elbow':    'Right Elbow',
        'right_hand':     'Right Hand',
        'chest':          'Chest',
        'abdomen':        'Abdomen',
        'pelvis':         'Pelvis',
        'left_hip':       'Left Hip',
        'right_hip':      'Right Hip',
        'left_thigh':     'Left Thigh',
        'right_thigh':    'Right Thigh',
        'left_knee':      'Left Knee',
        'right_knee':     'Right Knee',
        'left_shin':      'Left Shin',
        'right_shin':     'Right Shin',
        'left_foot':      'Left Foot',
        'right_foot':     'Right Foot',
        # ── Main body — back only ─────────────────────────────────────────
        'upper_back':    'Upper Back',
        'lower_back':    'Lower Back',
        'left_buttock':  'Left Buttock',
        'right_buttock': 'Right Buttock',
        # ── Left hand detail ──────────────────────────────────────────────
        'lhand_palm':   'Left Palm',
        'lhand_thumb':  'Left Thumb',
        'lhand_index':  'Left Index Finger',
        'lhand_middle': 'Left Middle Finger',
        'lhand_ring':   'Left Ring Finger',
        'lhand_pinky':  'Left Pinky Finger',
        # ── Right hand detail ─────────────────────────────────────────────
        'rhand_palm':   'Right Palm',
        'rhand_thumb':  'Right Thumb',
        'rhand_index':  'Right Index Finger',
        'rhand_middle': 'Right Middle Finger',
        'rhand_ring':   'Right Ring Finger',
        'rhand_pinky':  'Right Pinky Finger',
        # ── Left foot detail ──────────────────────────────────────────────
        'lfoot_upper':   'Left Upper Foot',
        'lfoot_sole':    'Left Sole',
        'lfoot_ball':    'Left Ball of Foot',
        'lfoot_big_toe': 'Left Big Toe',
        'lfoot_toe2':    'Left Toe 2',
        'lfoot_toe3':    'Left Toe 3',
        'lfoot_toe4':    'Left Toe 4',
        'lfoot_toe5':    'Left Toe 5 (Little)',
        # ── Right foot detail ─────────────────────────────────────────────
        'rfoot_upper':   'Right Upper Foot',
        'rfoot_sole':    'Right Sole',
        'rfoot_ball':    'Right Ball of Foot',
        'rfoot_big_toe': 'Right Big Toe',
        'rfoot_toe2':    'Right Toe 2',
        'rfoot_toe3':    'Right Toe 3',
        'rfoot_toe4':    'Right Toe 4',
        'rfoot_toe5':    'Right Toe 5 (Little)',
        # ── Head detail ───────────────────────────────────────────────────
        'hd_forehead':      'Forehead',
        'hd_crown':         'Crown',
        'hd_back_of_head':  'Back of Head',
        'hd_left_face':     'Left Face',
        'hd_right_face':    'Right Face',
        'hd_left_eye':      'Left Eye',
        'hd_right_eye':     'Right Eye',
        'hd_nose':          'Nose',
        'hd_mouth':         'Mouth',
        'hd_teeth':         'Teeth',
        'hd_mental_health': 'Mental Health',
    }

    @api.depends('incident_type_ids.code')
    def _compute_type_booleans(self):
        for rec in self:
            codes = rec.incident_type_ids.mapped('code')
            rec.is_injury = 'injury' in codes
            rec.is_illness = 'illness' in codes
            rec.is_vehicle = 'vehicle' in codes
            rec.is_plant_equipment = 'plant_equipment' in codes
            rec.is_drug_alcohol = 'drug_alcohol' in codes
            rec.is_buildings_grounds = 'buildings_grounds' in codes
            rec.is_security = 'security' in codes
            rec.is_theft = 'theft' in codes
            rec.is_environmental = 'environmental' in codes
            rec.is_psychosocial = 'psychosocial' in codes
            rec.is_it = 'it' in codes
            rec.is_complaint = 'complaint' in codes
            rec.is_child_safeguarding = 'child_safeguarding' in codes

    @api.depends('injury_body_parts')
    def _compute_body_parts_display(self):
        for rec in self:
            try:
                codes = json.loads(rec.injury_body_parts or '[]')
            except (json.JSONDecodeError, TypeError):
                codes = []
            parts = [self.BODY_PART_NAMES.get(c, c) for c in codes]
            rec.injury_body_parts_display = ', '.join(parts) if parts else ''

    @api.depends('corrective_action_ids', 'finding_ids')
    def _compute_counts(self):
        for rec in self:
            rec.corrective_action_count = len(rec.corrective_action_ids)
            rec.finding_count = len(rec.finding_ids)

    @api.depends('corrective_action_ids.state')
    def _compute_corrective_actions_complete(self):
        for rec in self:
            actions = rec.corrective_action_ids
            rec.corrective_actions_complete = bool(actions) and all(
                a.state == 'done' for a in actions)

    def _compute_attachment_count(self):
        Attachment = self.env['ir.attachment']
        for rec in self:
            rec.attachment_count = Attachment.search_count([
                ('res_model', '=', 'incident.report'),
                ('res_id', '=', rec.id),
            ])

    @api.depends('confidential_user_ids')
    def _compute_confidential_user_count(self):
        for rec in self:
            rec.confidential_user_count = len(rec.confidential_user_ids)

    @api.depends('employee_id')
    def _compute_from_employee(self):
        for rec in self:
            rec.department_id = rec.employee_id.department_id
            rec.job_title = rec.employee_id.job_title or ''

    # ── Kanban group expand ────────────────────────────────────────────────
    @api.model
    def _group_expand_states(self, states, domain):
        return [s[0] for s in self._fields['state'].selection]

    # ── Auto-confidential when Psychosocial category is selected ──────────
    _ALWAYS_CONFIDENTIAL_CODES = {'psychosocial', 'drug_alcohol', 'child_safeguarding'}

    @api.onchange('incident_type_ids')
    def _onchange_incident_type_ids_confidential(self):
        """Immediately flag the record as confidential in the UI when a
        category that requires confidentiality is added."""
        codes = {t.code for t in self.incident_type_ids}
        if codes & self._ALWAYS_CONFIDENTIAL_CODES and not self.is_confidential:
            self.is_confidential = True

    def _enforce_psychosocial_confidential(self):
        """Ensure any record tagged with a confidentiality-required category
        is always marked confidential."""
        for rec in self:
            codes = set(rec.incident_type_ids.mapped('code'))
            if codes & self._ALWAYS_CONFIDENTIAL_CODES and not rec.is_confidential:
                rec.sudo().write({'is_confidential': True})
                triggered = ', '.join(
                    c.replace('_', ' ').title()
                    for c in sorted(codes & self._ALWAYS_CONFIDENTIAL_CODES)
                )
                rec.message_post(
                    body=Markup(_('Automatically marked as <strong>Confidential</strong> '
                                  'because the following category was selected: %s.')) % triggered,
                    subtype_xmlid='mail.mt_note')

    # ── ORM ───────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'incident.report') or 'New'
        records = super().create(vals_list)
        records._enforce_psychosocial_confidential()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'incident_type_ids' in vals:
            self._enforce_psychosocial_confidential()
        return res

    # ── Workflow Actions ───────────────────────────────────────────────────
    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft incidents can be submitted.'))
            rec.state = 'submitted'
            rec.message_post(
                body=_('Incident report submitted and pending manager assignment.'),
                subtype_xmlid='mail.mt_note')

    def action_open_assign_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Assign Responsible Manager'),
            'res_model': 'incident.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_incident_id': self.id},
        }

    def action_start_investigation(self):
        for rec in self:
            if rec.state != 'assigned':
                raise UserError(_('The incident must be assigned before investigation can start.'))
            rec.write({
                'state': 'under_investigation',
                'investigation_start': fields.Date.today(),
            })
            rec.message_post(
                body=_('Investigation commenced.'),
                subtype_xmlid='mail.mt_note')

    def action_complete_investigation(self):
        for rec in self:
            if rec.state != 'under_investigation':
                raise UserError(_('Only incidents under investigation can be progressed.'))
            if not rec.investigation_conclusion:
                raise UserError(_(
                    'Please enter an Investigation Conclusion before completing the investigation.'))
            rec.write({
                'state': 'corrective_actions',
                'investigation_end': fields.Date.today(),
            })
            rec.message_post(
                body=_('Investigation completed. Corrective actions phase commenced.'),
                subtype_xmlid='mail.mt_note')

    def action_close(self):
        for rec in self:
            if rec.state != 'corrective_actions':
                raise UserError(_(
                    'The incident must be in the Corrective Actions state to close.'))
            if rec.corrective_action_ids and not rec.corrective_actions_complete:
                incomplete = rec.corrective_action_ids.filtered(
                    lambda a: a.state != 'done')
                raise UserError(_(
                    'Cannot close this incident — %d corrective action(s) are still open or '
                    'in progress. All corrective actions must be marked as Complete before '
                    'the incident can be closed.'
                ) % len(incomplete))
            rec.state = 'closed'
            rec.message_post(
                body=_('Incident closed.'),
                subtype_xmlid='mail.mt_note')

    def action_cancel(self):
        for rec in self:
            if rec.state == 'closed':
                raise UserError(_('Closed incidents cannot be cancelled.'))
            rec.state = 'cancelled'
            rec.message_post(
                body=_('Incident cancelled.'),
                subtype_xmlid='mail.mt_note')

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state not in ('submitted', 'cancelled'):
                raise UserError(_('Only submitted or cancelled incidents can be reset to draft.'))
            rec.state = 'draft'
            rec.message_post(
                body=_('Incident reset to draft.'),
                subtype_xmlid='mail.mt_note')

    def action_mark_confidential(self):
        """Enable confidentiality on this incident."""
        for rec in self:
            rec.is_confidential = True
            rec.message_post(
                body=Markup(_('Incident marked as <strong>Confidential</strong>. '
                              'Access is now restricted to authorised users only.')),
                subtype_xmlid='mail.mt_note')

    def action_remove_confidential(self):
        """Remove confidentiality from this incident."""
        for rec in self:
            rec.is_confidential = False
            rec.message_post(
                body=_('Confidential status removed. '
                       'This incident is now visible to all users with Incidents module access.'),
                subtype_xmlid='mail.mt_note')

    def action_manage_confidential_access(self):
        """Open the confidential access wizard for this incident."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manage Confidential Access'),
            'res_model': 'incident.confidential.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_incident_id': self.id,
                'default_user_ids': [(6, 0, self.confidential_user_ids.ids)],
            },
        }

    def action_view_attachments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Attachments'),
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('res_model', '=', 'incident.report'), ('res_id', '=', self.id)],
            'context': {'default_res_model': 'incident.report', 'default_res_id': self.id},
        }

    def action_open_report_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Export Incident Report PDF'),
            'res_model': 'incident.report.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_incident_id': self.id},
        }

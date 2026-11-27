{
    'name': 'Risk Management',
    'version': '19.0.1.20.0',
    'category': 'Operations/Risk Management',
    'summary': 'Risk assessment templates, risk assessments, a controls library and a risk matrix',
    'description': """
Risk Management
================
* Maintain a library of reusable Controls, Risk Categories, and Risk
  Types/Subtypes (each Subtype tiered under its Type). Controls can be
  linked to a Hierarchy of Controls level (e.g. Elimination, Substitution,
  Engineering Controls, Administrative Controls, PPE), ordered by sequence.
* Design one or more Risk Templates, each listing the risks relevant to an
  activity along with the controls that mitigate them.
* Build Risk Assessments by selecting one or more Risk Templates - their
  risks (and controls) are copied in automatically, ready to be tailored,
  or add risks manually.
* Configure a Risk Matrix from Likelihood, Consequence, Risk Severity and
  Risk Score reference data, including colour coding for severity bands
  that is applied to the matrix cells (with a separate text colour to
  keep labels readable against their background).
* Per-model access: every risk model (Risk Assessments, Risks, Risk
  Templates, Controls and each Configuration list) has its own View Only,
  Create, Update and Delete permissions, shown as e.g. "Risk Templates /
  Create". When Permission Management is installed, Administrator, Risk
  Manager, Manager, Employee and View Only roles are created from them.
  Users with Risk Assessments / Delete can also archive assessments and
  approve any submitted assessment. Risk Assessments / Create and Edit
  Own Only lets a user create and edit assessments but only see the ones
  they created or are the Owner, Approver or a Collaborator on, unless
  they also have Risk Assessments / Update or Delete.
* Risk Assessments carry a Risk Approver (defaulting to the Risk Assessment
  Owner's Team Leader) and a Review Due date (defaulting to one year after
  the assessment date), moving through a configurable Stage statusbar
  (Draft -> In Progress -> Submitted for Approval -> Approved -> Completed
  by default, editable from Configuration) with a popup dialogue to
  approve or reject a submitted assessment.
* Adds a Team Leader field to the Users form (under Related Partner),
  used to default a user's Risk Approver when they are the Risk Assessment Owner.
* Each Risk's "Fill Empty Fields by AI" button asks Claude (using the API
  key from the Claude AI settings) to fill in every empty field of the
  risk - Unwanted Event, Description, Risk Type/Subtype, Inherent and
  Residual Risk, Controls, Controls Summary and Actions - using its
  filled-in fields and the Summary of Activity as context. Fields that
  already have a value are left as they are.
* A Risk Assessment's "Generate Missing Risk Information" button runs
  "Fill Empty Fields by AI" on each of its risks that has empty fields,
  one after another.
* AI buttons only show once a Claude AI API key is set in General Settings.
* While an AI action runs, a progress overlay lists its steps and shows
  which one is running (e.g. which empty fields Claude is filling in).
* Controls without a description get one written by AI: by the AI risk
  actions (for the controls they add, as a step of their progress
  overlay), by the Control form's "Write Description by AI" button, or in
  the background by a scheduled job for controls added by hand - never
  while a record is being saved.
* Risk Template lines can list Standard Actions; when a Risk Assessment
  pulls a risk in from a template, those actions become Actions on the
  risk, assigned to the Risk Assessment Owner, each with a Due Date and an
  Open / Done / Cancelled status. Risks can also have ad-hoc Actions added
  directly. The Risk Assessment's "Open Actions" smart button shows its
  open Actions, and the Actions menu lists everyone's (My Actions by
  default).
* Risk Assessments and Risk Templates record Activity Details (location,
  Activity Leader, Safety Officer, Starting At / Finishing At), a Minimum
  Equipment / Facilities checklist and Governing Bodies / Associations /
  Legislation questions, each answered Yes, No or N/A with a Comments /
  Further Information box shown for Yes or No answers.
* A Risk Assessment can be exported to an A4 landscape PDF (the
  "Export to PDF" button), with the linked Company's branding in the
  header, the assessment's details, Activity Details and checklists on
  page 1, its Risks table starting on page 2, an Actions table starting on its own page, and "n of N" page
  numbers in the footer.
""",
    'author': 'Bendigo Scouts',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/risk_security.xml',
        'security/ir.model.access.csv',
        'data/risk_security_data.xml',
        'data/permission_role_sync.xml',
        'data/risk_matrix_data.xml',
        'data/risk_assessment_stage_data.xml',
        'data/risk_control_hierarchy_data.xml',
        'data/risk_control_cron.xml',
        'views/res_users_views.xml',
        'views/risk_category_views.xml',
        'views/risk_control_hierarchy_views.xml',
        'views/risk_control_views.xml',
        'views/risk_type_views.xml',
        'views/risk_subtype_views.xml',
        'views/risk_likelihood_views.xml',
        'views/risk_consequence_views.xml',
        'views/risk_severity_views.xml',
        'views/risk_score_views.xml',
        'views/risk_assessment_stage_views.xml',
        'views/risk_matrix_wizard_views.xml',
        'views/risk_template_line_views.xml',
        'views/risk_template_views.xml',
        'views/risk_assessment_line_views.xml',
        'views/risk_assessment_action_views.xml',
        'views/risk_assessment_approval_wizard_views.xml',
        'views/risk_assessment_views.xml',
        'views/risk_menus.xml',
        'report/risk_assessment_report_templates.xml',
        'report/risk_assessment_report_actions.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'risk_management/static/src/fields/risk_matrix_selector/risk_matrix_selector.js',
            'risk_management/static/src/fields/risk_matrix_selector/risk_matrix_selector.xml',
            'risk_management/static/src/fields/risk_matrix_selector/risk_matrix_selector.scss',
            'risk_management/static/src/fields/risk_score_badge/risk_score_badge.js',
            'risk_management/static/src/fields/risk_score_badge/risk_score_badge.xml',
            'risk_management/static/src/fields/risk_score_badge/risk_score_badge.scss',
            'risk_management/static/src/ai_progress/ai_progress.js',
            'risk_management/static/src/ai_progress/ai_progress.xml',
            'risk_management/static/src/ai_progress/ai_progress.scss',
            'risk_management/static/src/widgets/risk_ai_fill_button/risk_ai_fill_button.js',
            'risk_management/static/src/widgets/risk_ai_fill_button/risk_ai_fill_button.xml',
            'risk_management/static/src/widgets/risk_control_ai_describe_button/risk_control_ai_describe_button.js',
            'risk_management/static/src/widgets/risk_control_ai_describe_button/risk_control_ai_describe_button.xml',
            'risk_management/static/src/widgets/risk_ai_fill_all_button/risk_ai_fill_all_button.js',
            'risk_management/static/src/widgets/risk_ai_fill_all_button/risk_ai_fill_all_button.xml',
            'risk_management/static/src/widgets/risk_ai_generate_button/risk_ai_generate_button.js',
            'risk_management/static/src/widgets/risk_ai_generate_button/risk_ai_generate_button.xml',
            'risk_management/static/src/widgets/risk_ai_generate_button/risk_ai_generate_button.scss',
            'risk_management/static/src/scss/risk_lines_list.scss',
        ],
    },
    'installable': True,
    'application': True,
}

{
    'name': 'Risk Management',
    'version': '19.0.1.16.0',
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
* Risk Template lines can list Standard Actions; when a Risk Assessment
  pulls a risk in from a template, those actions become Odoo To-Do tasks
  (project.task, visible in the To-Do app) on the risk, assigned to the
  Risk Assessment Owner. Risks can also have ad-hoc Actions added
  directly. The Risk Assessment's "Actions" smart button shows every
  To-Do across the assessment's risks and the count still open.
* A Risk Assessment can be exported to an A4 landscape PDF (the
  "Export to PDF" button), with the linked Company's branding in the
  header, the assessment's details followed immediately by its Risks
  table, an Actions table starting on its own page, and "n of N" page
  numbers in the footer.
""",
    'author': 'Bendigo Scouts',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'project'],
    'data': [
        'security/access_levels.xml',
        'security/risk_security.xml',
        'security/ir.model.access.csv',
        'data/access_roles.xml',
        'data/risk_matrix_data.xml',
        'data/risk_assessment_stage_data.xml',
        'data/risk_control_hierarchy_data.xml',
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
            'risk_management/static/src/widgets/risk_ai_generate_button/risk_ai_generate_button.js',
            'risk_management/static/src/widgets/risk_ai_generate_button/risk_ai_generate_button.xml',
            'risk_management/static/src/widgets/risk_ai_generate_button/risk_ai_generate_button.scss',
            'risk_management/static/src/scss/risk_lines_list.scss',
        ],
    },
    'installable': True,
    'application': True,
}

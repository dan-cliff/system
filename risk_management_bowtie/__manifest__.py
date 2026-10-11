{
    'name': 'Risk Management - Bowtie Analysis',
    'version': '19.0.1.1.0',
    'category': 'Operations/Risk Management',
    'summary': 'Bowtie risk assessment on every risk, with a bowtie diagram and PDF appendices',
    'description': """
Risk Management - Bowtie Analysis
=================================
Adds a bowtie risk assessment to the Risks on Risk Templates and Risk
Assessments:

* The risk's Unwanted Event, relabelled Hazard, with the Risk itself as
  the Top Event; Threats with their Preventive Barriers, Consequences (with a severity) with their Recovery
  Barriers, and Escalation Factors on any barrier with their own
  Escalation Factor Barriers.
* Each barrier records its Barrier Type, Effectiveness, who is
  Accountable and, optionally, the library Control it represents. Barrier
  Types and Effectiveness ratings (with a colour) are editable under
  Configuration > Bowtie.
* The "Generate Bowtie Diagram" button shows the bowtie in a popup
  dialogue.
* Bowties are copied from a template into an assessment with its risks,
  and "Generate Risks and Controls by AI" fills in each risk's bowtie too.
* A Risk's "Fill Empty Fields by AI" button also fills in its Threats and
  Consequences (with their barriers) when it has none yet.
* The Risk Assessment PDF adds every risk's bowtie diagram as an appendix,
  one per page, titled with the risk.
""",
    'author': 'Bendigo Scouts',
    'license': 'LGPL-3',
    'depends': ['risk_management'],
    'data': [
        'security/ir.model.access.csv',
        'security/risk_bowtie_security.xml',
        'data/risk_bowtie_data.xml',
        'views/risk_bowtie_views.xml',
        'views/risk_line_views.xml',
        'views/risk_bowtie_menus.xml',
        'report/risk_assessment_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'risk_management_bowtie/static/src/actions/risk_bowtie_diagram/risk_bowtie_diagram.js',
            'risk_management_bowtie/static/src/actions/risk_bowtie_diagram/risk_bowtie_diagram.xml',
            'risk_management_bowtie/static/src/actions/risk_bowtie_diagram/risk_bowtie_diagram.scss',
        ],
    },
    'installable': True,
    'application': False,
}

{
    'name': 'Project - Risk Management',
    'version': '19.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Risk Assessments for projects',
    'description': """
        Installs automatically when both Project (advanced_projects) and Risk
        Management are installed.

        - Risk Assessments can belong to a project
        - A project's "New Risk Assessment" button starts one for the project
          (named after it, starting on its start date, with its colleagues as
          collaborators and its Company and Organisation)
        - The project lists its Risk Assessments under a smart button
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_projects', 'risk_management'],
    'data': [
        'views/risk_assessment_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

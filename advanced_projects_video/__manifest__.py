{
    'name': 'Project - Video Production',
    'version': '19.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Run a video production as an internal project',
    'description': """
        Installs automatically when both Project (advanced_projects) and Video
        Production are installed.

        - A video production's Project button creates a new internal project for
          it (from scratch or from a Project Template, dated up to the planned
          publish date) or links it to an existing internal project
        - Only internal projects (Project Types marked Internal) can be linked
        - The project shows its video productions under a smart button
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_projects', 'video_production'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/video_production_project_link_views.xml',
        'views/video_production_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

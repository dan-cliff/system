{
    'name': 'Project - Checklists',
    'version': '19.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Checklists to complete for project tasks',
    'description': """
        Installs automatically when both Project (advanced_projects) and
        Checklists are installed.

        - Checklist templates marked "Available in Projects" (Features tab)
          can be chosen as a task's Required Checklist
        - The task's "Start Checklist" button starts that checklist for the
          task (or opens the one already started); its checklists are listed
          on the task's Checklists tab
        - Checklists show the project and task they belong to
        - Completing a task's Required Checklist marks the task as done
        - The project lists the checklists completed for its tasks under a
          smart button
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_projects', 'checklists'],
    'data': [
        'views/checklist_views.xml',
        'views/advanced_project_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

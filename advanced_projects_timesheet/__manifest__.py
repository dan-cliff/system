{
    'name': 'Project - Timesheets',
    'version': '19.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Book timesheet hours to projects and their tasks',
    'description': """
        Installs automatically when both Project (advanced_projects) and Advanced
        Timesheets are installed.

        - Timesheet entries can be linked to a project, or to one of its tasks
          (which also links the project); on the timesheet grid each project /
          task gets its own row
        - Projects and tasks show the hours worked on them under an Hours smart
          button (the project's total includes its tasks), opening the entries
        - Two Overview widgets to add from Customize: "Project Working Hours
          Total" and "Project Working Hours by Person"
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_projects', 'advanced_timesheet'],
    'data': [
        'views/advanced_timesheet_line_views.xml',
        'views/advanced_project_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

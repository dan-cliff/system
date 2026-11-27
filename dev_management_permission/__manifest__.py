{
    'name': 'Development - Permission Management',
    'version': '19.0.1.1.0',
    'category': 'Services/Development',
    'summary': 'Standard Permission Management roles for Development',
    'description': """
        Installs automatically when both Development and Permission Management are
        installed, and adds these roles:

        - Development – Administrator: everything, including deleting anything, shipping
          releases and Configuration
        - Development – Manager: create and edit their own and their team's releases,
          sprints, epics, features, tickets and documentation; view every release, sprint,
          epic, feature and space
        - Development – Employee: create and edit their own releases, sprints, epics,
          features, tickets and documentation; view every release, sprint, epic, feature and
          space
        - Development – Developer: create, view and edit every ticket (work the shared
          board); view every release, feature and space; edit their own documentation
        - Development – Product Designer: create, view and edit every feature; view every
          release, ticket and space; edit their own documentation
        - Development – Release Manager: create, view and edit every release and ship them
          (Alpha, Beta and Core Release, merging branches, publishing on GitHub); view every
          feature, ticket and space

        - Development – Scrum Master: create, view and edit every sprint, epic and ticket, to
          plan, start and complete sprints; view every release, feature and space

        Viewing every release, sprint, epic, feature and space is added to the Manager and Employee
        roles so people can pick a release or feature on their tickets and read the team's
        documentation.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['dev_management', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

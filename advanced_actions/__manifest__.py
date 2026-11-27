{
    'name': 'Actions',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'One place for the actions raised in every app: assign, schedule, and complete with a checklist',
    'description': """
        Actions keeps the actions of every app in one table.

        - Each action has a Title, Description, Assigned To (any of the users can
          complete it), Due At, a Status bar, Created By / Created At, tags,
          priority, chatter and activities
        - Required Checklist: the action is completed by filling in a checklist
          from that template; completing the checklist completes the action
        - Duplicate for Users / Create for Several Users: give each of several
          users their own copy of an action (e.g. each completing their own
          checklist)
        - Notification Templates: emails when actions are assigned, due soon,
          overdue, done or cancelled. Hidden and not sent while Workflow
          Automation is installed, which sends notifications instead
        - Apps keep their own Actions menu, filtered to their actions (remove
          the filter to see every action). Checklists is built in; bridge
          modules install automatically for Incidents, Risk Management, Injury
          Management and Zoo Manager and move their existing actions in here
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['mail', 'hr', 'checklists'],
    'data': [
        'security/advanced_actions_security.xml',
        'security/ir.model.access.csv',
        'data/advanced_actions_data.xml',
        'data/advanced_action_notification_data.xml',
        'views/advanced_action_assign_wizard_views.xml',
        'views/advanced_action_views.xml',
        'views/advanced_action_tag_views.xml',
        'views/advanced_action_notification_views.xml',
        'views/advanced_actions_menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}

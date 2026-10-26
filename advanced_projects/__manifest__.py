{
    'name': 'Project',
    'version': '19.0.1.2.0',
    'category': 'Services/Project',
    'summary': 'Plan projects from templates, track tasks by phase and keep customers in the loop',
    'description': """
Project
=======
Rocketlane-style project management.

* Projects open as a list; Tasks > My Tasks / All Tasks list tasks across
  projects (Kanban, List, Gantt grouped by project).
* Each project has a configurable Overview
  dashboard, its Tasks as a Kanban, List or Gantt chart, Project Updates and
  its Team.
* Project plans: tasks are grouped under Phases and linked to each other in
  a many-to-many parent/child hierarchy (shown as arrows on the Gantt
  chart). Each link is End to Start, Start to Start, End to End or Start to
  End, set by dragging from a bar's start or end onto another bar's start or
  end. Plans are designed from scratch or created from a Project
  Template; any project can be saved as a template.
* Overview: add, remove, resize and drag widgets around (progress, task
  summary, phase progress, filtered task lists, tasks by stage, workload,
  team, latest update, notes).
* Project Updates: draft an update as a document of text blocks and task
  widgets (outstanding, upcoming, completed, blocked, overdue, milestones,
  custom), dragged in from a palette and filtered by phase, assignee and
  time window. Publishing freezes the task lists and shares the update.
* Team: invite anyone as a Colleague (added as a collaborator, permissions
  unchanged) or a Customer (a portal user who sees only the projects they
  are a Customer on). Missing customer permissions are flagged to the
  inviter, who can update them to the Project Customer permission set.
* Notification Templates (Configuration): emails when tasks are assigned,
  due soon, overdue or done, when updates are published or projects change
  stage. Hidden and not sent while Workflow Automation is installed, which
  sends project notifications as workflows instead.
* Project Types (Configuration) mark projects as internal or external.
* Budget: each project's Budget tab allocates hours and money in budget lines
  (by Budget Category and phase) and records what was spent, compared with
  the hours planned on tasks (and worked, with Advanced Timesheets) and shown
  by the Overview's Budget widget. Employees only.
* Chatter on projects, tasks and updates for everyone with access to the
  project (customers through the portal). Comments can be marked Private,
  so only employees see them.
* Permissions per CLAUDE.md: a privilege per project permission and per task
  permission, plus "Project Updates: Publish" and "Projects: Manage Customer
  Access"; phases, updates and the team follow their project, and tasks follow
  their project as well as their own task permissions. Standard roles ship in
  advanced_projects_permission.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['mail', 'portal', 'hr'],
    'data': [
        'security/advanced_projects_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/mail_message_subtype_data.xml',
        'data/advanced_project_option_data.xml',
        'data/mail_template_data.xml',
        'data/advanced_project_template_data.xml',
        'data/advanced_project_notification_data.xml',
        'views/advanced_project_option_views.xml',
        'views/advanced_project_task_views.xml',
        'views/advanced_project_phase_views.xml',
        'views/advanced_project_update_views.xml',
        'views/advanced_project_update_templates.xml',
        'views/advanced_project_overview_widget_views.xml',
        'views/advanced_project_collaborator_views.xml',
        'views/advanced_project_views.xml',
        'views/advanced_project_notification_views.xml',
        'views/advanced_project_portal_templates.xml',
        'wizard/advanced_project_invite_views.xml',
        'wizard/advanced_project_from_template_views.xml',
        'views/advanced_projects_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_projects/static/src/scss/backend.scss',
            'advanced_projects/static/src/gantt/*',
            'advanced_projects/static/src/overview/*',
            'advanced_projects/static/src/update_editor/*',
            'advanced_projects/static/src/chatter/*',
            'advanced_projects/static/src/components/*',
        ],
        'web.assets_frontend': [
            'advanced_projects/static/src/scss/portal.scss',
        ],
    },
    'installable': True,
    'application': True,
}

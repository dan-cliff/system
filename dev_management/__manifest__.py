{
    'name': 'Development',
    'version': '19.0.1.1.0',
    'category': 'Services/Development',
    'summary': 'Plan, build, document and ship software: releases, features, tickets, documentation and GitHub',
    'description': """
Development
===========
Jira and Confluence, built into Odoo.

* Releases: a two-week sprint followed by Alpha, Beta and Core releases, moving through
  Draft, Open, Documentation, Review, Complete, Alpha Release, Beta Release, Core Release,
  Closed (or Cancelled). Start Date is the first Monday after creation; the other dates
  follow from it (lengths set in Settings) and can be changed. Date Closed is filled in
  when the release is closed. Reaching Review creates the next release of the cycle.
* Release numbers YYYY.MM.NNN (the NNNth release of the month), counted from the release
  tags on GitHub and the releases in Odoo, and changeable by hand. A draft release is
  opened on GitHub when the release is created; "Merge Branches" merges the branches of
  the release's tickets and features into release/<number>, and "Publish on GitHub"
  publishes the release.
* AI release names: with a naming prompt in Settings (e.g. "Stars and planets") each new
  release is named by the AI, with Trivia about the name. AI release notes too.
* Repositories: GitHub repositories, each with its own access token (Administrators
  only), Test Connection and Sync Branches.
* Features: problem and goals, technical specification, acceptance criteria, research and
  third-party documentation, with its tickets and branches. AI drafts the specification
  (then reruns it with additional context), researches the feature on the web (adding the
  sources it used to Third-party Documentation), reworks any selected text from a floating
  AI button, and breaks a feature into tickets.
* Tickets, like Jira issues: types, priorities, a board of configurable stages, sub-tasks,
  links between tickets (blocks, relates to, duplicates, ...), story points, estimates,
  labels, acceptance criteria (AI can write them), backlog, release, feature and GitHub
  branches ("Create Branch" creates one on GitHub).
* Documentation, like Confluence: spaces with a tree of pages written collaboratively,
  page templates, full page history with restore, links to releases, features and tickets.
* Reporting on tickets and releases.
* AI features show only when a Claude (preferred) or Google Gemini key is set in General
  Settings or in the Odoo AI app; neither app is needed.
* Permissions per CLAUDE.md: a privilege per permission on Releases, Features, Tickets and
  Documentation Spaces, a "Releases: Ship" workflow privilege and the Development
  Administrator; standard roles ship in dev_management_permission.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['mail', 'hr', 'web_hierarchy', 'base_setup'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/dev_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/dev_sequence.xml',
        'data/dev_option_data.xml',
        'data/dev_cron.xml',
        'views/dev_option_views.xml',
        'views/dev_repository_views.xml',
        'views/dev_release_views.xml',
        'views/dev_feature_views.xml',
        'views/dev_ticket_views.xml',
        'views/dev_space_views.xml',
        'views/res_config_settings_views.xml',
        'views/dev_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dev_management/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
}

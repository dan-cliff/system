{
    'name': 'Feature Suggestions',
    'version': '19.0.1.0.0',
    'category': 'Services/Development',
    'summary': 'Collect, vote on and prioritise ideas from customers and colleagues, with a website forum',
    'description': """
Feature Suggestions
===================
Like Microsoft User Voice or Productboard, built on Development.

* Suggestions from customers (the website forum at /feature-requests), colleagues and
  the Helpdesk, with categories, statuses (New, Under Review, Planned, In Progress,
  Released, Not Planned, Merged) and sources, all configurable.
* Votes with how important it is (Nice to have / Important / Critical, each with a weight)
  and why it matters: each suggestion gets a vote count and a weighted score.
* Website forum: browse by category and status, search, sort by Top, Newest, Trending
  (votes in the last 30 days) or Most Discussed, vote, comment and post new ideas.
  Visitors browse; signing in lets them vote, comment and post.
* Moderation: status changes (followers and voters are told), publishing, an official
  response shown on the website, merging duplicates (votes move across) and turning a
  suggestion into a Feature.
* Linked to Development Features and Tickets; when a release delivering a suggestion
  reaches Core Release the suggestion is marked Released and its voters hear about it.
* AI triage (when a Claude or Gemini key is set): summary, category and possible
  duplicates and related features.
* Installs automatically with Development and can be uninstalled on its own.
* Permissions per CLAUDE.md: a privilege per permission on suggestions, a "Moderate"
  workflow privilege and the Feature Suggestions Administrator; standard roles ship in
  dev_feature_suggestions_permission.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['dev_management', 'website'],
    'data': [
        'security/suggestion_security.xml',
        'security/ir.model.access.csv',
        'data/suggestion_data.xml',
        'views/dev_suggestion_option_views.xml',
        'views/dev_suggestion_views.xml',
        'views/website_templates.xml',
        'views/res_config_settings_views.xml',
        'views/dev_suggestion_menus.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'dev_feature_suggestions/static/src/scss/feature_requests.scss',
        ],
    },
    # Installed with Development (pulling in Website); Development doesn't depend on it.
    'auto_install': ['dev_management'],
    'installable': True,
    'application': True,
}

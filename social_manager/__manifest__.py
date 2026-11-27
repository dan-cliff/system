{
    'name': 'Social Manager',
    'version': '19.0.1.0.1',
    'category': 'Marketing/Social Manager',
    'summary': 'Manage Facebook, X, LinkedIn, Instagram, TikTok and YouTube pages: posts, '
               'scheduling, comments, moderation, monetisation and AI insights',
    'description': """
Social Manager
==============
* Platforms (Facebook, X (Twitter), LinkedIn, Instagram, TikTok and YouTube)
  each hold their own OAuth app credentials. "Connect an Account" signs in with
  the platform's OAuth flow and imports every Page / Channel the account can
  manage.
* Create posts for one or more Pages / Channels, publish them now or schedule
  them, with an approval step for users who may only draft.
* Likes, reactions, comments, shares and views are synchronised from each
  platform; comments can be replied to, hidden or deleted from Odoo.
* Permissions are created automatically for every Platform and every Page /
  Channel: Create and Edit Draft, Create and Edit Published, Approve Posts,
  Moderate Posts and Delete Posts. A level on a Platform covers all of its
  Pages / Channels. When Permission Management is installed a role is created
  for each level as well.
* Platforms and Pages / Channels can be flagged as monetised; income is
  tracked per post and totalled per Page / Channel and per Platform.
* Settings > Social Manager > Integrations:

  - Integrate to Accounts: creates one customer invoice per Platform for a
    date range of monetised income, with a line per Page / Channel. The link
    is kept on the Social Manager side; the invoice only gets the references
    as text in its line descriptions.
  - AI Analysis: comment sentiment, moderation flags, recommended actions and
    post performance ranking, using the AI keys from General Settings.
  - AI Recommendations: a weekly scheduled action asks the AI for proposed
    posts (draft copy and action items) for upcoming special events and
    company releases, building on the best performing posts. Proposals are
    listed as "Proposed" for a user to accept or dismiss.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['base_setup', 'mail', 'account', 'claude_ai_settings'],
    'data': [
        'security/social_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/social_sentiment_data.xml',
        'data/social_income_type_data.xml',
        'data/social_event_type_data.xml',
        'data/social_platform_data.xml',
        'data/social_access_sync.xml',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'views/social_platform_views.xml',
        'views/social_account_views.xml',
        'views/social_channel_views.xml',
        'views/social_post_views.xml',
        'views/social_publication_views.xml',
        'views/social_comment_views.xml',
        'views/social_income_views.xml',
        'views/social_invoice_views.xml',
        'views/social_event_views.xml',
        'views/social_option_views.xml',
        'wizard/social_comment_reply_wizard_views.xml',
        'wizard/social_invoice_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/social_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'social_manager/static/src/ai_progress/ai_progress.js',
            'social_manager/static/src/ai_progress/ai_progress.xml',
            'social_manager/static/src/ai_progress/ai_progress.scss',
            'social_manager/static/src/ai_job/ai_job_action.js',
        ],
    },
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': True,
}

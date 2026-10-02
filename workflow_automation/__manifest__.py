# Part of Cliff's Country Crafts. See LICENSE file for full copyright and licensing details.

{
    'name': 'Workflow Automation Engine',
    'version': '19.0.1.1.0',
    'summary': 'Complex multi-step workflow automation triggered by model events or schedules',
    'description': """
Workflow Automation Engine
==========================

A powerful, configurable workflow automation engine for Odoo 19.0.

Features:
---------
* Multi-step workflows triggered by record create/write/unlink events or on a schedule
* Step types: create record, update record, delete record, add activity, post message,
  send notification (bus), send email, execute Python code, conditional branch,
  stop workflow, trigger sub-workflow
* Per-step condition checks (domain or Python expression)
* Field value mapping with static, expression, record field path, or context variable sources
* Anti-recursion guard to prevent infinite loops
* Full execution logging with per-step timing and error capture
* Manual run wizard for ad-hoc execution
* Per-model access levels (View Only, Create, Create and Edit Own Only, Update,
  Delete), all in the Administrator role; internal users can read workflows
    """,
    'author': "Cliff's Country Crafts",
    'category': 'Technical',
    'license': 'OPL-1',
    'depends': [
        'base',
        'mail',
        'report_builder',
    ],
    'data': [
        'security/access_levels.xml',
        'security/ir.model.access.csv',
        'data/access_roles.xml',
        'data/workflow_cron_data.xml',
        'views/workflow_automation_views.xml',
        'views/workflow_step_views.xml',
        'views/workflow_execution_log_views.xml',
        'views/workflow_manual_run_wizard_views.xml',
        'views/wf_service_platform_views.xml',
        'views/wf_api_call_log_views.xml',
        'views/wf_step_connection_views.xml',
        'views/workflow_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'workflow_automation/static/src/js/workflow_canvas_action.js',
            'workflow_automation/static/src/xml/workflow_canvas.xml',
            'workflow_automation/static/src/scss/workflow_canvas.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}

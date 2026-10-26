from odoo.tools import html2plaintext, plaintext2html

from . import models


def post_init_hook(env):
    """Move the existing Risk Assessment actions into Actions."""
    Action = env['advanced.action']

    def vals(old):
        return {
            'risk_line_id': old.line_id.id,
            'name': old.name,
            'description': plaintext2html(old.description) if old.description else False,
            'user_ids': [(6, 0, old.user_id.ids)],
            'date_deadline': Action._date_to_deadline(old.date_deadline, old.user_id or old.create_uid),
            'state': old.state,
            'company_id': old.company_id.id or env.company.id,
        }

    Action._transfer_records(env['risk.assessment.action'].search([]), 'advanced.action', vals)


def uninstall_hook(env):
    """Move the risks' actions back to Risk Management's own actions, and
    point its menu back at them."""
    Action = env['advanced.action']

    def vals(action):
        user = action.user_ids[:1]
        return {
            'line_id': action.risk_line_id.id,
            'name': action.name,
            'description': html2plaintext(action.description) if action.description else False,
            'user_id': user.id,
            'date_deadline': Action._deadline_to_date(action.date_deadline, user or action.create_uid),
            'state': 'open' if action.state == 'in_progress' else action.state,
        }

    actions = Action.with_context(active_test=False).search([('risk_line_id', '!=', False)])
    Action._transfer_records(actions, 'risk.assessment.action', vals)
    menu = env.ref('risk_management.menu_risk_actions', raise_if_not_found=False)
    old_action = env.ref('risk_management.action_risk_assessment_action', raise_if_not_found=False)
    if menu and old_action:
        menu.action = old_action

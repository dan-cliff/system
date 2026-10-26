from odoo import fields
from odoo.tools import plaintext2html

from . import models

# Former corrective action Control Types -> Control Type records.
CONTROL_TYPES = ('eliminate', 'substitute', 'engineering', 'administrative', 'ppe', 'other')
STATES_IN = {'open': 'open', 'in_progress': 'in_progress', 'done': 'done'}
STATES_OUT = {'open': 'open', 'in_progress': 'in_progress', 'done': 'done', 'cancelled': 'done'}


def _control_type(env, code):
    return env.ref(f'advanced_actions_incident.control_type_{code}', raise_if_not_found=False)


def post_init_hook(env):
    """Move the existing corrective actions into Actions."""
    Action = env['advanced.action']

    def vals(old):
        control_type = old.action_type and _control_type(env, old.action_type)
        return {
            'name': (old.name or '').strip().split('\n')[0][:250] or 'Corrective action',
            'description': plaintext2html(old.name or ''),
            'incident_id': old.incident_id.id,
            'icam_finding_id': old.icam_finding_id.id,
            'control_type_id': control_type.id if control_type else False,
            'priority': old.priority or '0',
            'user_ids': [(6, 0, old.responsible_id.ids)],
            'date_deadline': Action._date_to_deadline(old.due_date, old.create_uid),
            'state': STATES_IN.get(old.state, 'open'),
            'date_done': Action._date_to_deadline(old.completion_date, old.create_uid),
            'verification_required': old.verification_required,
            'verified_by_id': old.verified_by_id.id,
            'verification_date': old.verification_date,
            'completion_notes': old.notes,
        }

    Action._transfer_records(env['incident.corrective.action'].search([]), 'advanced.action', vals)


def uninstall_hook(env):
    """Move the incidents' actions back to Incidents' own corrective actions,
    and point its menu back at them."""
    Action = env['advanced.action']

    def vals(action):
        control_type = action.control_type_id
        code = next((c for c in CONTROL_TYPES if _control_type(env, c) == control_type), False) if control_type else False
        user = action.user_ids[:1] or action.create_uid
        return {
            'incident_id': action.incident_id.id,
            'icam_finding_id': action.icam_finding_id.id,
            'name': action.name,
            'action_type': code or ('other' if control_type else False),
            'priority': action.priority or '0',
            'responsible_id': user.id,
            'due_date': Action._deadline_to_date(action.date_deadline, user) or fields.Date.today(),
            'state': STATES_OUT[action.state],
            'completion_date': Action._deadline_to_date(action.date_done, user),
            'verification_required': action.verification_required,
            'verified_by_id': action.verified_by_id.id,
            'verification_date': action.verification_date,
            'notes': action.completion_notes,
        }

    actions = Action.with_context(active_test=False).search([('incident_id', '!=', False)])
    Action._transfer_records(actions, 'incident.corrective.action', vals)
    menu = env.ref('incident_management.menu_corrective_actions', raise_if_not_found=False)
    old_action = env.ref('incident_management.action_incident_corrective_action_all', raise_if_not_found=False)
    if menu and old_action:
        menu.action = old_action


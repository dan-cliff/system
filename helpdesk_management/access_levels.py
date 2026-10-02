"""Helpdesk access levels - see permission_management/access_levels_lib.py.

Regenerate the security files after changing this: python3 tools/generate_access_levels.py helpdesk_management
"""

APP_NAME = 'Helpdesk'
PREFIX = 'helpdesk'
CATEGORY = 'base.module_category_services_helpdesk'

OPERATIONAL, CONFIG, SETTINGS = 'operational', 'config', 'settings'

MODELS = [
    # An agent's own tickets: those assigned to them or in a team they belong to.
    ('ticket', 'Tickets', OPERATIONAL, {
        'model_helpdesk_ticket': ['user_id', 'team_id.member_ids'],
        'model_helpdesk_sla_status': ['ticket_id.user_id', 'ticket_id.team_id.member_ids'],
    }, []),
    ('team', 'Helpdesk Teams', CONFIG, ['model_helpdesk_team'], []),
    ('stage', 'Helpdesk Stages', CONFIG, ['model_helpdesk_stage'], []),
    ('sla', 'SLA Policies', CONFIG, ['model_helpdesk_sla'], []),
    ('ticket_type', 'Ticket Types', CONFIG, ['model_helpdesk_ticket_type'], []),
    ('tag', 'Helpdesk Tags', CONFIG, ['model_helpdesk_tag'], []),
]

# Portal customers read their company's tickets (see the portal record rule).
EXTRA_ACCESS = [
    ('access_helpdesk_ticket_portal', 'model_helpdesk_ticket', 'base.group_portal', 'r'),
    ('access_helpdesk_team_portal', 'model_helpdesk_team', 'base.group_portal', 'r'),
    ('access_helpdesk_stage_portal', 'model_helpdesk_stage', 'base.group_portal', 'r'),
    ('access_helpdesk_ticket_type_portal', 'model_helpdesk_ticket_type', 'base.group_portal', 'r'),
]

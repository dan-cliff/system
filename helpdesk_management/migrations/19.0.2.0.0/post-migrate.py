"""19.0.2.0.0: per-permission access model, ticket metrics.

- Helpdesk "User" became the technical base group: on its own it gives no
  ticket access. Its members keep what they could do before (create, view and
  edit every ticket) through "Tickets: Create and Edit All".
- Date Raised is new: existing tickets were raised when they were created.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    base_group = env.ref('helpdesk_management.group_helpdesk_user')
    edit_all = env.ref('helpdesk_management.group_helpdesk_ticket_edit_all')
    users = base_group.with_context(active_test=False).user_ids.filtered(lambda u: not u.share)
    if users:
        edit_all.write({'user_ids': [(4, user.id) for user in users]})

    cr.execute("UPDATE helpdesk_ticket SET date_raised = create_date WHERE create_date IS NOT NULL")
    tickets = env['helpdesk.ticket'].with_context(active_test=False).search([])
    env.add_to_compute(tickets._fields['days_open'], tickets)
    env.add_to_compute(tickets._fields['days_to_resolution'], tickets)
    tickets._recompute_recordset(['days_open', 'days_to_resolution'])

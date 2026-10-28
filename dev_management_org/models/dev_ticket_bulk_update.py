from odoo import fields, models

from odoo.addons.org_structure.models.org_scope_mixin import ORG_LEVELS


class DevTicketBulkUpdate(models.TransientModel):
    # The Organisation fields (with their cascading levels) to set on the
    # tickets; not scoped, and not defaulted from the user's home units.
    _name = 'dev.ticket.bulk.update'
    _inherit = ['dev.ticket.bulk.update', 'org.scope.mixin']
    _org_scoped = False

    update_org = fields.Boolean('Change Organisation')

    def _bulk_apply(self, tickets):
        super()._bulk_apply(tickets)
        if not self.update_org:
            return
        given = [level for level in ORG_LEVELS if self[f'org_{level}_id']]
        if not given:
            # Ticked and left empty: clear the tickets' Organisation.
            tickets.write({f'org_{level}_id': False for level in ORG_LEVELS})
            return
        # The levels picked (and those above them) are set; a ticket keeps
        # a lower unit only when it belongs to the new ones.
        lowest = given[-1]
        upper = ORG_LEVELS[:ORG_LEVELS.index(lowest) + 1]
        vals = {f'org_{level}_id': self[f'org_{level}_id'].id for level in upper}
        for ticket in tickets:
            ticket_vals = dict(vals)
            for lower in ORG_LEVELS[len(upper):]:
                unit = ticket[f'org_{lower}_id']
                if unit and any(unit[f'{level}_id'] and unit[f'{level}_id'].id != vals[f'org_{level}_id']
                                for level in upper):
                    ticket_vals[f'org_{lower}_id'] = False
            ticket.write(ticket_vals)

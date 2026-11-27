# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class ManufacturingDashboard(models.AbstractModel):
    """Data for the Manufacturing Dashboard (static/src/dashboard): what needs
    doing today and what each work centre is doing. Counts respect the user's
    permissions."""
    _name = 'advanced.manufacturing.dashboard'
    _description = 'Manufacturing Dashboard'

    @api.model
    def _dashboard_cards(self):
        now = fields.Datetime.now()
        week_ago = now - timedelta(days=7)
        open_states = ('confirmed', 'progress', 'to_close')
        return [
            ('draft', 'To Confirm', [('state', '=', 'draft')], 'info'),
            ('waiting', 'Waiting for Components',
             [('state', '=', 'confirmed'), ('reservation_state', 'not in', ('assigned',))], 'warning'),
            ('ready', 'Ready to Start', [('state', '=', 'confirmed'), ('reservation_state', '=', 'assigned')], 'success'),
            ('progress', 'In Progress', [('state', 'in', ('progress', 'to_close'))], 'primary'),
            ('late', 'Late', [('state', 'in', open_states), ('date_deadline', '<', now)], 'danger'),
            ('done', 'Produced (Last 7 Days)', [('state', '=', 'done'), ('date_finished', '>=', week_ago)], 'muted'),
        ]

    @api.model
    def get_data(self):
        Production = self.env['mrp.production']
        cards = [{
            'key': key,
            'label': self.env._(label),
            'domain': domain,
            'tone': tone,
            'count': Production.search_count(domain),
        } for key, label, domain, tone in self._dashboard_cards()]

        Workorder = self.env['mrp.workorder']
        workcenters = []
        can_open = self.env.user.has_group('mrp.group_mrp_user')
        for workcenter in self.env['mrp.workcenter'].search([], limit=50):
            orders = Workorder.search([
                ('workcenter_id', '=', workcenter.id),
                ('state', 'in', ('blocked', 'ready', 'progress')),
                ('production_state', 'not in', ('draft', 'done', 'cancel')),
            ])
            running = orders.filtered(lambda wo: wo.state == 'progress')
            workcenters.append({
                'id': workcenter.id,
                'name': workcenter.name,
                'code': workcenter.code or '',
                'working_state': workcenter.working_state,
                'progress': len(running),
                'queued': len(orders - running),
                'workers': running.sudo().working_employee_ids.mapped('name'),
                'url': workcenter.terminal_url if can_open else False,
                'last_contact': fields.Datetime.to_string(workcenter.sudo().terminal_last_contact)
                if workcenter.sudo().terminal_last_contact else False,
                'failed': workcenter.sudo().terminal_failed_count,
            })
        return {
            'cards': cards,
            'workcenters': workcenters,
            'can_create': Production.has_access('create'),
        }

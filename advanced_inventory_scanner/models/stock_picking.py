# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def scanner_walk_pickings(self, kind):
        """Ready transfers for the Scanner's Pick ('pick') or Put Away ('putaway') screens."""
        domain = [('state', '=', 'assigned')]
        if kind == 'putaway':
            domain += ['|', ('picking_type_code', '=', 'incoming'), '&', ('picking_type_code', '=', 'internal'),
                       ('location_dest_id.usage', '=', 'internal')]
        else:
            domain += [('picking_type_code', 'in', ('outgoing', 'internal'))]
        pickings = self.search(domain, order='priority desc, scheduled_date, id', limit=200)
        pickings = pickings.filtered(lambda p: p.walk_kind == kind)
        return [{
            'id': picking.id,
            'name': picking.name,
            'partner': picking.partner_id.display_name or '',
            'origin': picking.origin or '',
            'type': picking.picking_type_id.name,
            'lines': len(picking.move_line_ids),
            'scheduled': fields.Datetime.context_timestamp(picking, picking.scheduled_date).strftime('%d/%m/%Y %H:%M')
            if picking.scheduled_date else '',
            'late': bool(picking.scheduled_date and picking.scheduled_date < fields.Datetime.now()),
        } for picking in pickings]

    @api.model
    def scanner_find_picking(self, name, kind):
        """A ready transfer by its scanned name, for the pickers."""
        picking = self.search([('name', '=', (name or '').strip()), ('state', '=', 'assigned')], limit=1)
        return picking.id if picking and picking.walk_kind == kind else False

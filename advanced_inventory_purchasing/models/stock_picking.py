# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import _, models
from odoo.tools import formatLang


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        res = super()._action_done()
        for picking in self.filtered(lambda p: p.picking_type_code == 'incoming' and p.purchase_id and p.state == 'done'):
            picking._inventory_note_on_order()
        return res

    def _inventory_note_on_order(self):
        """Tell the purchase order what was received into inventory, and where."""
        self.ensure_one()
        lines = self.move_line_ids.filtered(lambda l: l.quantity)
        if not lines:
            return
        rows = Markup('').join(
            Markup('<li>%s × %s %s → <b>%s</b>%s</li>') % (
                formatLang(self.env, line.quantity, digits=2).rstrip('0').rstrip('.'),
                line.product_id.display_name,
                line.product_uom_id.name,
                line.location_dest_id.display_name,
                Markup(' (%s)') % escape(line.lot_id.name or line.lot_name) if (line.lot_id or line.lot_name) else '',
            ) for line in lines.sorted(lambda l: (l.walk_sequence, l.id)))
        body = Markup('<p>%s</p><ul>%s</ul>') % (
            _('Received into inventory with %(receipt)s:', receipt=self.name), rows)
        self.purchase_id.sudo().message_post(body=body, subtype_xmlid='mail.mt_note')

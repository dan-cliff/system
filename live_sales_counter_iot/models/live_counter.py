from odoo import fields, models


class LiveCounter(models.Model):
    _inherit = 'live.counter'

    display_ids = fields.One2many('iot.node', 'live_counter_id', string='Display Screens')
    display_count = fields.Integer(compute='_compute_display_count')

    def _compute_display_count(self):
        for counter in self:
            counter.display_count = len(counter.sudo().display_ids.filtered(
                lambda n: n.display_content == 'live_counter'))

    def action_view_displays(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('embroidery_jobbing.action_embroidery_display_nodes')
        action['domain'] = [('role', '=', 'embroidery_display'), ('live_counter_id', '=', self.id),
                            ('display_content', '=', 'live_counter')]
        action['context'] = {'default_role': 'embroidery_display', 'default_display_content': 'live_counter',
                             'default_live_counter_id': self.id}
        return action

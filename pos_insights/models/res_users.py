from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _load_pos_data_read(self, records, config):
        read_records = super()._load_pos_data_read(records, config)
        if read_records:
            # Only the logged-in user is loaded (see point_of_sale's domain).
            read_records[0]['_pos_insights'] = self.env.user.has_group('pos_insights.group_pos_insights')
        return read_records

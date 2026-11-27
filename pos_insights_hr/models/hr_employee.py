from odoo import api, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def _load_pos_data_read(self, records, config):
        read_records = super()._load_pos_data_read(records, config)
        allowed = records.sudo().filtered(
            lambda emp: emp.user_id and emp.user_id.has_group('pos_insights.group_pos_insights')
        ).ids
        for employee in read_records:
            employee['_pos_insights'] = employee['id'] in allowed
        return read_records

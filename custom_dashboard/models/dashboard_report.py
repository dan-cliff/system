from odoo import api, models


class ReportDashboard(models.AbstractModel):
    _name = 'report.custom_dashboard.report_dashboard'
    _description = 'Dashboard PDF Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        return {
            'doc_ids': docids,
            'doc_model': 'custom.dashboard',
            'docs': self.env['custom.dashboard'].browse(docids),
            'data': data,
            'company': self.env['res.company'].browse(data.get('company_id')) or self.env.company,
        }

from odoo import api, models


class ReportPosInsightsOrders(models.AbstractModel):
    _name = 'report.pos_insights.report_pos_insights_orders'
    _description = 'POS Insights - Session Orders'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        # From the POS the session comes in `data` (with the cashier, so
        # their permission can be checked); printed from the backend it
        # comes as docids.
        session_ids = docids or ([data['session_id']] if data.get('session_id') else [])
        sessions = self.env['pos.session'].browse(session_ids)
        sessions._check_pos_insights_access(data.get('employee_id') or False)
        return {
            'doc_ids': sessions.ids,
            'doc_model': 'pos.session',
            'docs': sessions,
        }

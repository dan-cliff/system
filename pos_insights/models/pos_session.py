from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _get_pos_insights_user(self, employee_id=False):
        """The user whose "POS Insights" permission decides access: the
        logged-in user here; pos_insights_hr swaps in the cashier
        employee's linked user when the POS uses employee login."""
        return self.env.user

    def _check_pos_insights_access(self, employee_id=False):
        users = [session._get_pos_insights_user(employee_id) for session in self] or [self.env.user]
        if not all(user and user.has_group('pos_insights.group_pos_insights') for user in users):
            raise AccessError(_("You need the \"POS Insights\" permission to print session reports."))

    def get_pos_insights_report_action(self, report_code, employee_id=False):
        """Return the report action for one of the POS Insights reports,
        limited to this (current) session. Called from the POS front end;
        ``employee_id`` is the logged-in cashier when the POS uses
        employee login (pos_hr)."""
        self.ensure_one()
        self._check_pos_insights_access(employee_id)
        if self.state == 'closed':
            raise UserError(_("Reports can only be printed for the current, open session."))

        if report_code == 'orders':
            # Passed as data (not docids) so the report can re-check the
            # cashier's permission when the PDF is rendered.
            data = {'session_id': self.id, 'employee_id': employee_id}
            return self.env.ref('pos_insights.action_report_pos_insights_orders').report_action(
                self, data=data, config=False)

        sale_details = self.env.ref('point_of_sale.sale_details_report')
        if report_code == 'sales_details':
            # The backend Sales Details wizard, run for this POS from the
            # session's opening time until now.
            data = {
                'date_start': fields.Datetime.to_string(self.start_at or fields.Datetime.now()),
                'date_stop': fields.Datetime.to_string(fields.Datetime.now()),
                'config_ids': self.config_id.ids,
                'session_ids': False,
            }
            return sale_details.report_action([], data=data, config=False)
        if report_code == 'session':
            # Same data as the backend Session Report wizard
            # (pos.daily.sales.reports.wizard) for this session.
            data = {
                'date_start': False,
                'date_stop': False,
                'config_ids': self.config_id.ids,
                'session_ids': self.ids,
            }
            return sale_details.report_action([], data=data, config=False)
        raise UserError(_("Unknown report: %s", report_code))

    def _get_pos_insights_orders(self):
        self.ensure_one()
        return self.order_ids.filtered(lambda o: o.state != 'cancel').sorted('date_order')

    def _get_pos_insights_product_summary(self):
        """Quantity and sales per product for the session's orders."""
        self.ensure_one()
        groups = self.env['pos.order.line']._read_group(
            [('order_id', 'in', self._get_pos_insights_orders().ids)],
            groupby=['product_id'],
            aggregates=['qty:sum', 'price_subtotal:sum', 'price_subtotal_incl:sum'],
        )
        summary = [{
            'product': product.display_name,
            'qty': qty,
            'subtotal': subtotal,
            'subtotal_incl': subtotal_incl,
        } for product, qty, subtotal, subtotal_incl in groups]
        return sorted(summary, key=lambda line: -line['subtotal_incl'])

from odoo import http
from odoo.http import request


class EmployeeHealthcareController(http.Controller):

    def _resolve_my_healthcare(self):
        """Look up (or create) the current user's healthcare record and return
        a redirect to /odoo/healthcare/<id>.  Falls back to the list view if
        the user has no linked employee record."""
        env = request.env.sudo()
        employee = env['hr.employee'].search(
            [('user_id', '=', request.env.uid)], limit=1,
        )
        if not employee:
            return request.redirect('/odoo/healthcare')

        healthcare = env['employee.healthcare'].search(
            [('employee_id', '=', employee.id)], limit=1,
        )
        if not healthcare:
            healthcare = env['employee.healthcare'].create(
                {'employee_id': employee.id}
            )

        return request.redirect(f'/odoo/healthcare/{healthcare.id}')

    @http.route('/healthcare/my', auth='user', type='http')
    def my_healthcare_profile(self):
        """Handle bookmarked /healthcare/my shortcut URL."""
        return self._resolve_my_healthcare()

    @http.route('/odoo/healthcare/my', auth='user', type='http')
    def my_healthcare_profile_odoo(self):
        """Handle /odoo/healthcare/my — catches the case where the SPA would
        otherwise interpret 'my' as a record slug and show an error."""
        return self._resolve_my_healthcare()

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def _kiosk_current_capabilities(self, courses=None):
        """Return the Learning capabilities each employee currently holds.

        A capability is current when the employee has a completed training
        record for the course that has not expired.

        :param courses: optional ``lms.course`` recordset to limit the check to
        :return: ``{employee_id: {course_id: expiry_date or False}}`` where
            ``False`` means the capability never expires. When an employee
            holds several current records for a course, the latest expiry wins.
        """
        result = {employee.id: {} for employee in self}
        if not self:
            return result
        today = fields.Date.context_today(self)
        domain = [
            ('employee_id', 'in', self.ids),
            ('state', '=', 'completed'),
            '|', ('expiry_date', '=', False), ('expiry_date', '>=', today),
        ]
        if courses is not None:
            if not courses:
                return result
            domain.append(('course_id', 'in', courses.ids))
        records = self.env['lms.employee.record'].sudo().search_read(
            domain, ['employee_id', 'course_id', 'expiry_date'],
        )
        for rec in records:
            held = result[rec['employee_id'][0]]
            course_id = rec['course_id'][0]
            expiry = rec['expiry_date']
            if course_id not in held:
                held[course_id] = expiry
            elif held[course_id] and (not expiry or expiry > held[course_id]):
                held[course_id] = expiry
        return result

from odoo import models, fields, _


class MailActivityPlan(models.Model):
    _inherit = 'mail.activity.plan'

    course_group_ids = fields.Many2many(
        'lms.course.group',
        'lms_activity_plan_course_group_rel',
        'plan_id',
        'course_group_id',
        string='Training Packages',
        help='Training packages that will be automatically assigned to the employee when this plan is launched.',
    )


class MailActivitySchedule(models.TransientModel):
    _inherit = 'mail.activity.schedule'

    def action_schedule_plan(self):
        result = super().action_schedule_plan()
        if self.res_model == 'hr.employee' and self.plan_id.course_group_ids:
            applied_on = self._get_applied_on_records()
            for employee in applied_on:
                for course_group in self.plan_id.course_group_ids:
                    self.env['lms.course.group.assignment'].create({
                        'employee_id': employee.id,
                        'course_group_id': course_group.id,
                    })
                employee.message_post(
                    body=_(
                        'Training packages assigned via plan "%(plan)s": %(packages)s',
                        plan=self.plan_id.name,
                        packages=', '.join(self.plan_id.course_group_ids.mapped('name')),
                    )
                )
        return result

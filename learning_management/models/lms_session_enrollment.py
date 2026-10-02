from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError


class LmsSessionEnrollment(models.Model):
    _name = 'lms.session.enrollment'
    _description = 'LMS Session Enrolment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'session_id, employee_id'

    session_id = fields.Many2one(
        'lms.course.session', string='Session', required=True, ondelete='cascade', tracking=True
    )
    course_id = fields.Many2one(related='session_id.course_id', store=True, string='Course')
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade', tracking=True
    )
    manager_id = fields.Many2one(
        'hr.employee',
        string='Manager',
        compute='_compute_manager',
        store=True,
    )

    state = fields.Selection([
        ('pending_approval', 'Pending Manager Approval'),
        ('confirmed', 'Confirmed'),
        ('attended', 'Attended'),
        ('absent', 'No Show'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='confirmed', required=True, tracking=True)

    enrolled_by = fields.Many2one(
        'res.users', string='Enrolled By', default=lambda self: self.env.user, readonly=True
    )
    is_self_enrolled = fields.Boolean(string='Self-Enrolled', default=False, readonly=True)
    approval_required = fields.Boolean(string='Approval Required', default=False)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True, tracking=True)
    approved_date = fields.Datetime(string='Approved On', readonly=True)

    notes = fields.Text(string='Notes')

    _unique_enrollment = models.Constraint(
        'UNIQUE(session_id, employee_id)',
        'This employee is already enrolled in this session.',
    )

    @api.depends('employee_id')
    def _compute_manager(self):
        for rec in self:
            rec.manager_id = rec.employee_id.parent_id if rec.employee_id else False

    def action_confirm(self):
        """The employee's manager, or a user with Session Enrolments / Update, confirms a
        pending enrolment."""
        can_confirm_any = self.env.user.has_group('learning_management.group_lms_enrollment_update')
        for rec in self:
            if rec.state != 'pending_approval':
                raise UserError(_('Only pending enrolments can be confirmed.'))
            if not can_confirm_any and rec.manager_id.user_id != self.env.user:
                raise AccessError(_("Only the employee's manager can confirm this enrolment."))
            rec.write({
                'state': 'confirmed',
                'approved_by': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            })
            rec.employee_id.message_post(
                body=_('Your enrolment in <b>%s</b> has been approved.') % rec.session_id.name,
                subtype_xmlid='mail.mt_note',
            )

    def action_cancel(self):
        for rec in self:
            rec.write({'state': 'cancelled'})

    def action_mark_attended(self):
        for rec in self:
            if rec.state == 'confirmed':
                rec.write({'state': 'attended'})

    def action_mark_absent(self):
        for rec in self:
            if rec.state == 'confirmed':
                rec.write({'state': 'absent'})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.state == 'pending_approval' and rec.manager_id:
                # Notify manager
                manager_user = rec.manager_id.user_id
                if manager_user:
                    rec.session_id.message_post(
                        body=_(
                            '<b>%(employee)s</b> has requested to enrol in this session and requires '
                            'your approval. <a href="/odoo/learning/enrollments/%(enroll_id)s">Review request</a>.'
                        ) % {'employee': rec.employee_id.name, 'enroll_id': rec.id},
                        partner_ids=[manager_user.partner_id.id],
                        subtype_xmlid='mail.mt_comment',
                    )
        return records

from odoo import fields, models


class LmsScormApproval(models.Model):
    _name = 'lms.scorm.approval'
    _description = 'SCORM Course Approval'
    _order = 'round desc, id'

    course_id = fields.Many2one(
        'lms.scorm.course', string='Course', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='course_id.company_id', store=True)
    round = fields.Integer(string='Submission', required=True, default=1)
    user_id = fields.Many2one(
        'res.users', string='Approver',
        help='Empty means any Approver can give this approval.')
    decided_by_id = fields.Many2one('res.users', string='Decided By', readonly=True)
    state = fields.Selection([
        ('pending', 'Waiting'),
        ('approved', 'Approved'),
        ('rejected', 'Changes Requested'),
        ('cancelled', 'Cancelled'),
    ], string='Decision', default='pending', required=True)
    decision_date = fields.Datetime(string='Decided On', readonly=True)
    note = fields.Text(string='Comments')

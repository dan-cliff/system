from odoo import fields, models


class LmsScormApprovalWizard(models.TransientModel):
    _name = 'lms.scorm.approval.wizard'
    _description = 'Approve or Request Changes to a SCORM Course'

    course_id = fields.Many2one('lms.scorm.course', string='Course', required=True, ondelete='cascade')
    open_comment_count = fields.Integer(related='course_id.open_comment_count')
    note = fields.Text(string='Comments', help='Required when requesting changes.')

    def action_approve(self):
        self.ensure_one()
        self.course_id.action_approve(self.note)
        return {'type': 'ir.actions.act_window_close'}

    def action_reject(self):
        self.ensure_one()
        self.course_id.action_reject(self.note)
        return {'type': 'ir.actions.act_window_close'}

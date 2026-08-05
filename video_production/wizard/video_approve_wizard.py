# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class VideoApproveWizard(models.TransientModel):
    """Bulk approve or refuse selected reviews."""
    _name = 'video.approve.wizard'
    _description = 'Approve / Refuse Reviews'

    review_ids = fields.Many2many(
        'video.review',
        string='Reviews',
        default=lambda self: self.env.context.get('active_ids'),
    )
    action = fields.Selection(
        [('approve', 'Approve All'), ('refuse', 'Refuse All')],
        string='Action',
        required=True,
        default='approve',
    )
    comment = fields.Text(string='Comment / Feedback')

    def action_confirm(self):
        for review in self.review_ids:
            approver = review.approver_ids.filtered(
                lambda a: a.user_id == self.env.user
            )
            if not approver and not self.env.user.has_group(
                'video_production.group_video_production_manager'
            ):
                raise UserError(
                    _('You are not listed as an approver for review "%s".') % review.name
                )
            now = fields.Datetime.now()
            status = 'approved' if self.action == 'approve' else 'refused'
            approver.write({'status': status, 'date_acted': now, 'comment': self.comment})
            if self.action == 'approve' and review.all_approved:
                review.state = 'approved'
            elif self.action == 'refuse':
                review.state = 'refused'
        return {'type': 'ir.actions.act_window_close'}

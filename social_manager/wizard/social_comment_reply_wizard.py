from odoo import fields, models


class SocialCommentReplyWizard(models.TransientModel):
    _name = 'social.comment.reply.wizard'
    _description = 'Reply to a Social Comment'

    comment_id = fields.Many2one('social.comment', required=True, readonly=True)
    comment_message = fields.Text(related='comment_id.message', string='Comment Text')
    author_name = fields.Char(related='comment_id.author_name', string='Author')
    message = fields.Text(string='Reply', required=True)

    def action_send(self):
        self.ensure_one()
        self.comment_id._send_reply(self.message)
        return {'type': 'ir.actions.act_window_close'}

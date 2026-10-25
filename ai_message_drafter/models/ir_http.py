from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Tell the web client whether an AI key is set, so the chatter only
        shows the AI Message button when there is an AI to call."""
        session_info = super().session_info()
        if self.env.user._is_internal():
            session_info['ai_message_drafter_enabled'] = bool(
                self.env['ai.message.drafter']._providers())
        return session_info

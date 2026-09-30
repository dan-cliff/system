from odoo import api, models


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    @api.model
    def message_route(self, message, message_dict, model=None, thread_id=None, custom_values=None):
        """A reply that came back through a tokenized reply-to address goes to
        the record the original email was sent from, whatever alias or
        references it carries (see mandrill.mail.log._process_inbound_one)."""
        force = self.env.context.get('mandrill_force_thread')
        if force and not message_dict.get('is_bounce'):
            force_model, force_id = force
            record = self.env[force_model].browse(force_id).exists() if force_model in self.env else None
            if record and hasattr(record, 'message_update'):
                user_id = self._mail_find_user_for_gateway(message_dict['email_from']).id or self.env.uid
                route = self._routing_check_route(
                    message, message_dict, (force_model, force_id, None, user_id, self.env['mail.alias']),
                    raise_exception=False)
                if route:
                    return [route]
        return super().message_route(message, message_dict, model=model, thread_id=thread_id,
                                     custom_values=custom_values)

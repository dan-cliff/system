from odoo import _, models
from odoo.exceptions import AccessError, UserError
from odoo.addons.mail.tools.discuss import Store

# Records whose chatter offers Private comments.
PRIVATE_CHATTER_MODELS = ('advanced.project', 'advanced.project.task', 'advanced.project.update')


class AdvancedProjectPrivateChatterMixin(models.AbstractModel):
    """Private comments: a message posted with "Private" ticked is stored as
    Employee Only (mail.message.is_internal), which Odoo already hides from
    portal and public users everywhere (backend and portal chatter). Its
    notifications go to employees only."""
    _name = 'advanced.project.private.chatter.mixin'
    _description = 'Project Private Comments'
    _inherit = ['mail.thread']

    def _get_allowed_message_params(self):
        return super()._get_allowed_message_params() | {'is_internal'}

    def message_post(self, **kwargs):
        # only employees choose who may see a comment
        if 'is_internal' in kwargs and not self.env.user._is_internal() and not self.env.su:
            kwargs.pop('is_internal')
        return super().message_post(**kwargs)

    def _notify_get_recipients(self, message, msg_vals=False, **kwargs):
        recipients = super()._notify_get_recipients(message, msg_vals=msg_vals, **kwargs)
        is_internal = (msg_vals or {}).get('is_internal', message.sudo().is_internal)
        if is_internal:
            recipients = [r for r in recipients if not r.get('share') and r.get('id')]
        return recipients


class MailMessage(models.Model):
    _inherit = 'mail.message'

    def _to_store_defaults(self, target):
        fields = super()._to_store_defaults(target)
        if target.is_internal(self.env):
            # employees see which comments are Private
            fields.append(Store.Attr(
                'advanced_project_private',
                value=lambda m: (bool(m.is_internal) and m.model in PRIVATE_CHATTER_MODELS
                                 and m.message_type in ('comment', 'email')),
            ))
        return fields

    def advanced_project_set_private(self, private):
        """Mark comments on projects, tasks and updates as Private (employees
        only) or not. Employees who can edit the record, or wrote the comment,
        may change it."""
        for message in self:
            if not self.env.user._is_internal():
                raise AccessError(_('Only employees can change who sees a comment.'))
            if message.model not in PRIVATE_CHATTER_MODELS or message.message_type not in ('comment', 'email'):
                raise UserError(_('Only comments on projects, tasks and updates can be made private.'))
            record = self.env[message.model].browse(message.res_id).exists()
            if not record:
                continue
            if message.author_id != self.env.user.partner_id:
                record.check_access('write')
            else:
                record.check_access('read')
            # sudo: checked above; mail.message itself is only writable by its author
            message.sudo().is_internal = bool(private)
        return True

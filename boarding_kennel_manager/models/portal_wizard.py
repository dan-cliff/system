from odoo import models


class PortalWizardUser(models.TransientModel):
    _inherit = 'portal.wizard.user'

    def _as_kennel_portal_user(self):
        """Customer Portal Users may invite customers without being allowed to edit contacts; the invitation
        still has to save the email it's sent to and build the customer's sign-up link, which need that."""
        if self.env.user.has_group('boarding_kennel_manager.group_kennel_portal_user'):
            return self.sudo()
        return self

    def _update_partner_email(self):
        return super(PortalWizardUser, self._as_kennel_portal_user())._update_partner_email()

    def _send_email(self):
        return super(PortalWizardUser, self._as_kennel_portal_user())._send_email()

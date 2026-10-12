from odoo.tests import new_test_user
from odoo.tests.common import TransactionCase


class SocialCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.platform = cls.env.ref('social_manager.platform_facebook')
        cls.platform.write({'client_id': 'app', 'client_secret': 'secret'})
        cls.account = cls.env['social.account'].create({
            'name': 'Test Account', 'platform_id': cls.platform.id, 'external_id': 'u1',
            'access_token': 'user-token',
        })
        Channel = cls.env['social.channel']
        cls.page_a = Channel.create({'name': 'Page A', 'platform_id': cls.platform.id,
                                     'account_id': cls.account.id, 'external_id': 'pa', 'access_token': 'ta'})
        cls.page_b = Channel.create({'name': 'Page B', 'platform_id': cls.platform.id,
                                     'account_id': cls.account.id, 'external_id': 'pb', 'access_token': 'tb'})
        cls.drafter = new_test_user(cls.env, 'sm_drafter', groups='base.group_user')
        cls.publisher = new_test_user(cls.env, 'sm_publisher', groups='base.group_user')
        cls.approver = new_test_user(cls.env, 'sm_approver', groups='base.group_user')
        cls.outsider = new_test_user(cls.env, 'sm_outsider', groups='base.group_user')
        cls.drafter.group_ids = [(4, cls.page_a.group_draft_id.id)]
        cls.publisher.group_ids = [(4, cls.platform.group_publish_id.id), (4, cls.platform.group_delete_id.id)]
        cls.approver.group_ids = [(4, cls.page_a.group_approve_id.id), (4, cls.page_a.group_moderate_id.id)]
        cls.outsider.group_ids = [(4, cls.page_b.group_draft_id.id)]

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestSocialInvoice(AccountTestInvoicingCommon):

    def test_one_invoice_per_platform_line_per_channel(self):
        self.env.user.group_ids = [(4, self.env.ref('social_manager.group_social_manager').id)]
        env = self.env
        env['ir.config_parameter'].sudo().set_param('social_manager.integrate_accounts', 'True')
        youtube = env.ref('social_manager.platform_youtube').sudo()
        facebook = env.ref('social_manager.platform_facebook').sudo()
        youtube.write({'is_monetised': True, 'partner_id': self.partner_a.id, 'company_id': self.env.company.id})
        facebook.write({'is_monetised': True, 'partner_id': self.partner_b.id, 'company_id': self.env.company.id})
        youtube, facebook = youtube.sudo(False), facebook.sudo(False)
        Channel = env['social.channel']
        yt1 = Channel.create({'name': 'Channel One', 'platform_id': youtube.id, 'is_monetised': True})
        yt2 = Channel.create({'name': 'Channel Two', 'platform_id': youtube.id, 'is_monetised': True})
        fb = Channel.create({'name': 'FB Page', 'platform_id': facebook.id, 'is_monetised': True})
        Income = env['social.income']
        for channel, amount, day in ((yt1, 10, 5), (yt1, 15, 20), (yt2, 7, 9), (fb, 3, 1), (yt1, 99, 30)):
            Income.create({'name': 'Ads', 'channel_id': channel.id, 'amount': amount,
                           'date': fields.Date.to_date('2026-09-%02d' % min(day, 30))})
        outside = Income.create({'name': 'Ads', 'channel_id': yt1.id, 'amount': 50,
                                 'date': fields.Date.to_date('2026-10-02')})
        self.assertEqual(yt1.income_total, 10 + 15 + 99 + 50)
        self.assertEqual(youtube.income_total, 10 + 15 + 99 + 50 + 7)

        invoices = env['social.invoice']._create_invoices(
            fields.Date.to_date('2026-09-01'), fields.Date.to_date('2026-09-30'), youtube | facebook)
        self.assertEqual(len(invoices), 2)
        yt_invoice = invoices.filtered(lambda i: i.platform_id == youtube)
        move = yt_invoice.move_id
        self.assertEqual(move.move_type, 'out_invoice')
        self.assertEqual(move.partner_id, self.partner_a)
        self.assertEqual(len(move.invoice_line_ids), 2)
        self.assertEqual(sorted(move.invoice_line_ids.mapped('price_unit')), [7, 124])
        one = move.invoice_line_ids.filtered(lambda l: l.price_unit == 124)
        self.assertIn('Platform: YouTube', one.name)
        self.assertIn('Page / Channel: Channel One', one.name)
        self.assertIn('01/09/2026 to 30/09/2026', one.name)
        self.assertEqual(yt_invoice.line_ids.filtered(lambda l: l.channel_id == yt1).move_line_id, one)
        self.assertFalse(outside.invoiced)
        with self.assertRaises(UserError):
            yt1.income_ids.filtered('invoiced')[0].amount = 1
        # Nothing left to invoice in that range.
        again = env['social.invoice']._create_invoices(
            fields.Date.to_date('2026-09-01'), fields.Date.to_date('2026-09-30'), youtube)
        self.assertFalse(again)

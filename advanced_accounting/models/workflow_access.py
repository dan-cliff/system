"""The workflow permissions of Accounting (see CLAUDE.md > Permissions).

Confirming and posting assets, approving budgets, confirming recurring
payments and closing periods are not plain edits: each needs its own
permission, checked here before the action, and the action then writes with
sudo() so the record rules of the editing permissions don't get in its way.
Scheduled actions run as the superuser and are not checked.
"""
from odoo import _, models
from odoo.exceptions import AccessError


def _check_workflow(records, group, action):
    if records.env.su or records.env.user.has_group(f'advanced_accounting.{group}'):
        return
    privilege = records.env.ref(f'advanced_accounting.{group}').privilege_id
    raise AccessError(records.env._(
        'You are not allowed to %(action)s: it needs the "%(privilege)s" permission.',
        action=action, privilege=privilege.name,
    ))


class AccountAssetAsset(models.Model):
    _inherit = 'account.asset.asset'

    def validate(self):
        _check_workflow(self, 'group_asset_post', _('confirm assets'))
        return super(AccountAssetAsset, self.sudo()).validate()

    def set_to_close(self):
        _check_workflow(self, 'group_asset_post', _('dispose of assets'))
        return super(AccountAssetAsset, self.sudo()).set_to_close()

    def set_to_draft(self):
        _check_workflow(self, 'group_asset_post', _('reset assets to draft'))
        return super(AccountAssetAsset, self.sudo()).set_to_draft()


class AccountAssetDepreciationLine(models.Model):
    _inherit = 'account.asset.depreciation.line'

    def create_move(self, post_move=True):
        _check_workflow(self, 'group_asset_post', _('post depreciation entries'))
        return super(AccountAssetDepreciationLine, self.sudo()).create_move(post_move=post_move)

    def post_lines_and_close_asset(self):
        _check_workflow(self, 'group_asset_post', _('post depreciation entries'))
        return super(AccountAssetDepreciationLine, self.sudo()).post_lines_and_close_asset()


class AssetDepreciationConfirmationWizard(models.TransientModel):
    _inherit = 'asset.depreciation.confirmation.wizard'

    def asset_compute(self):
        _check_workflow(self, 'group_asset_post', _('generate the asset entries'))
        return super(AssetDepreciationConfirmationWizard, self.sudo()).asset_compute()


class AssetModify(models.TransientModel):
    _inherit = 'asset.modify'

    def modify(self):
        _check_workflow(self, 'group_asset_post', _('modify running assets'))
        return super(AssetModify, self.sudo()).modify()


class AssetSell(models.TransientModel):
    _inherit = 'asset.sell'

    def action_confirm(self):
        _check_workflow(self, 'group_asset_post', _('sell or dispose of assets'))
        return super(AssetSell, self.sudo()).action_confirm()


class CrossoveredBudget(models.Model):
    _inherit = 'crossovered.budget'

    def action_budget_confirm(self):
        _check_workflow(self, 'group_budget_approve', _('confirm budgets'))
        return super(CrossoveredBudget, self.sudo()).action_budget_confirm()

    def action_budget_draft(self):
        _check_workflow(self, 'group_budget_approve', _('reset budgets to draft'))
        return super(CrossoveredBudget, self.sudo()).action_budget_draft()

    def action_budget_validate(self):
        _check_workflow(self, 'group_budget_approve', _('approve budgets'))
        return super(CrossoveredBudget, self.sudo()).action_budget_validate()

    def action_budget_cancel(self):
        _check_workflow(self, 'group_budget_approve', _('cancel budgets'))
        return super(CrossoveredBudget, self.sudo()).action_budget_cancel()

    def action_budget_done(self):
        _check_workflow(self, 'group_budget_approve', _('close budgets'))
        return super(CrossoveredBudget, self.sudo()).action_budget_done()


class RecurringPayment(models.Model):
    _inherit = 'recurring.payment'

    def action_done(self):
        _check_workflow(self, 'group_recurring_confirm', _('confirm recurring payments'))
        return super(RecurringPayment, self.sudo()).action_done()

    def action_draft(self):
        _check_workflow(self, 'group_recurring_confirm', _('reset recurring payments to draft'))
        return super(RecurringPayment, self.sudo()).action_draft()

    def action_stop(self):
        _check_workflow(self, 'group_recurring_confirm', _('stop recurring payments'))
        return super(RecurringPayment, self.sudo()).action_stop()

    def action_generate_payment(self):
        _check_workflow(self, 'group_recurring_confirm', _('generate recurring payments'))
        return super(RecurringPayment, self.sudo()).action_generate_payment()


class RecurringPaymentLine(models.Model):
    _inherit = 'recurring.payment.line'

    def action_create_payment(self):
        _check_workflow(self, 'group_recurring_confirm', _('generate recurring payments'))
        return super(RecurringPaymentLine, self.sudo()).action_create_payment()

    def action_skip(self):
        _check_workflow(self, 'group_recurring_confirm', _('skip recurring payments'))
        return super(RecurringPaymentLine, self.sudo()).action_skip()

    def action_reset(self):
        _check_workflow(self, 'group_recurring_confirm', _('reset recurring payments'))
        return super(RecurringPaymentLine, self.sudo()).action_reset()


class AccountPeriodClosing(models.Model):
    _inherit = 'account.period.closing'

    def action_close(self):
        _check_workflow(self, 'group_closing_close', _('close periods'))
        return super(AccountPeriodClosing, self.sudo()).action_close()

    def action_reopen(self):
        _check_workflow(self, 'group_closing_close', _('reopen periods'))
        return super(AccountPeriodClosing, self.sudo()).action_reopen()

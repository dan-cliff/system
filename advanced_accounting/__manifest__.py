{
    'name': 'Accounting',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'sequence': 1,
    'summary': 'Full accounting: assets, budgets, recurring payments, period closing, '
               'follow-ups and the financial reports',
    'description': """
        Accounting

        A modern replacement for the Odoo Mates accounting suite
        (om_account_accountant and the modules it installs), on the same
        models, so the apps built on those models keep working:

        - Assets: asset categories, depreciation boards, depreciation entries,
          disposal and sale, assets created from vendor bills, asset analysis
        - Budgets: budgetary positions, budgets and budget analysis
        - Recurring Payments: recurring templates and payments, auto-posted entries
        - Period Closing: closing checks and tasks, lock dates, fiscal years and
          the year-end closing
        - Follow-ups: payment follow-up plans, reminders, customer and vendor
          statements, follow-up analysis
        - Reporting: Balance Sheet, Profit and Loss, Cash Flow Statement, Annual
          Report, General and Partner Ledgers, Trial Balance, Aged Partner
          Balance, Tax Report and closing, Journals Audit, Day / Cash / Bank Books
        - Credit limits that can block posting, with an override permission
        - A Reports menu where Report Builder saves the app's custom reports

        Taking over Odoo Mates: installed on a database that has the Odoo Mates
        accounting modules, Accounting takes over their records (assets,
        budgets, recurring payments, fiscal years, follow-up plans, financial
        reports, ...) and marks those modules as uninstalled without dropping
        anything. Their pending data upgrades are applied, and the users of the
        accounting groups get the matching Accounting permissions. Install
        Accounting before removing them: uninstalling an Odoo Mates module on
        its own deletes its records. Afterwards, the Odoo Mates accounting
        modules can't be installed again next to Accounting.

        Access: one permission per record type and operation (Create Only,
        Create and Edit Own / My Team / All, View All, Delete Own / All) plus
        Confirm and Post (assets), Approve (budgets), Confirm and Generate
        (recurring payments) and Close and Reopen (period closings), and an
        Administrator. The financial reports and the follow-ups keep the core
        accounting groups.

        Based on the Odoo Mates accounting modules (LGPL-3), by Odoo Mates and Odoo SA.
    """,
    'author': "Cliff's Country Crafts, Odoo Mates, Odoo SA",
    'depends': ['account', 'analytic', 'mail', 'hr', 'base_setup'],
    'data': [
        'security/group.xml',
        'security/advanced_accounting_security.xml',
        'security/ir.model.access.csv',
        'security/account_asset_security.xml',
        'security/security.xml',
        'security/security_followup.xml',
        'security/security_fiscal.xml',
        'security/security_recurring.xml',
        'data/res_lang_data.xml',
        # reports
        'data/account_account_type.xml',
        'views/menu.xml',
        'views/ledger_menu.xml',
        'views/financial_report.xml',
        'views/account_account_views.xml',
        'wizard/account_report_common_view.xml',
        'wizard/partner_ledger.xml',
        'wizard/general_ledger.xml',
        'wizard/trial_balance.xml',
        'wizard/balance_sheet.xml',
        'wizard/profit_and_loss.xml',
        'wizard/tax_report.xml',
        'wizard/tax_closing.xml',
        'wizard/aged_partner.xml',
        'wizard/journal_audit.xml',
        'wizard/cash_flow.xml',
        'wizard/annual_report.xml',
        'report/report_style.xml',
        'report/report.xml',
        'report/report_partner_ledger.xml',
        'report/report_general_ledger.xml',
        'report/report_trial_balance.xml',
        'report/report_financial.xml',
        'report/report_annual.xml',
        'report/report_tax.xml',
        'report/report_aged_partner.xml',
        'report/report_journal_audit.xml',
        'report/report_journal_entries.xml',
        'report/report_cash_flow.xml',
        # daily reports
        'views/om_daily_reports.xml',
        'wizard/daybook.xml',
        'wizard/cashbook.xml',
        'wizard/bankbook.xml',
        'report/reports.xml',
        'report/report_daybook.xml',
        'report/report_cashbook.xml',
        'report/report_bankbook.xml',
        # assets
        'data/account_asset_data.xml',
        'wizard/asset_depreciation_confirmation_wizard_views.xml',
        'wizard/asset_modify_views.xml',
        'wizard/asset_sell_views.xml',
        'views/account_asset_views.xml',
        'views/account_move_views.xml',
        'views/asset_category_views.xml',
        'views/product_views.xml',
        'report/account_asset_report_views.xml',
        # budgets
        'views/account_analytic_account_views.xml',
        'views/account_budget_views.xml',
        'views/res_config_settings_views.xml',
        # follow-ups
        'data/mail_template_data.xml',
        'data/mail_activity_type_data.xml',
        'data/ir_cron.xml',
        'wizard/followup_print_view.xml',
        'wizard/followup_results_view.xml',
        'wizard/followup_send_views.xml',
        'views/followup_view.xml',
        'views/account_move.xml',
        'views/partners.xml',
        'views/report_followup.xml',
        'views/reports.xml',
        'views/followup_partner_view.xml',
        'report/customer_statement.xml',
        'report/followup_report.xml',
        'data/mail_template_statement_data.xml',
        # fiscal years and period closing
        'data/period_closing_task_data.xml',
        'wizard/change_lock_date.xml',
        'wizard/fiscal_year_closing.xml',
        'views/fiscal_year.xml',
        'views/period_closing.xml',
        'views/settings_fiscal.xml',
        # recurring payments
        'data/sequence.xml',
        'data/recurring_cron.xml',
        'data/mail_activity_type_data_recurring.xml',
        'views/recurring_template_view.xml',
        'views/recurring_payment_view.xml',
        'views/auto_post_views.xml',
        # the app
        'views/review_menu.xml',
        'views/settings_accountant.xml',
        'views/account_group.xml',
        'views/account_tag.xml',
        'views/res_partner.xml',
        'views/account_bank_statement.xml',
        'views/payment_method.xml',
        'views/reconciliation.xml',
        'views/account_journal.xml',
        'views/menu_accountant.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_accounting/static/src/scss/account_asset.scss',
        ],
    },
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}

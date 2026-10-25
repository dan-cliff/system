{
    'name': 'CRM',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Leads, opportunities, quotes and e-signed contracts, modelled on Salesforce',
    'description': """
CRM (modern_crm)
================
A sales CRM modelled on Salesforce Leads and Opportunities. Its technical
name is modern_crm so it never clashes with Odoo's standard crm app.

* Leads: capture prospects by hand, by import, from the Web-to-Lead form
  (/crm/web-to-lead, switched on in Settings) or by email (point a mail alias
  at the Lead model). Nurture them through New, Working and Nurturing with
  activities, ratings (Hot / Warm / Cold) and sources, then convert them into
  an Account, a Contact and an Opportunity, or disqualify them with a reason.
* Opportunities: a pipeline by stage with probability, amount, expected
  revenue, close date, forecast category, next step and guidance for success
  on every stage. Products (opportunity lines) total the amount; contact
  roles record who decides, buys and influences. Closed Won / Closed Lost
  (with a lost reason).
* Quotes: generate a Sales quotation from the opportunity's products. The
  opportunity's primary quote is the one its contracts and sales order use.
  Confirming a quote can mark the opportunity Closed Won.
* Contracts: generated from contract templates (with placeholders for the
  account, opportunity and quote), with a start date and term. Send them
  for digital signature: each signer (the customer, and a countersigner from
  your company) gets a private link, signs in the browser in turn, or
  declines with a reason. The signed PDF is stored on the contract and
  emailed to every signer.
* When a contract is fully signed it can activate itself, confirm its
  quote into a Sales Order and draft the Invoice (each switched on in
  Settings). The opportunity's buttons do the same by hand. With
  subscription_oca, modern_crm_subscription shows the Subscriptions those
  sales orders create.
* Permissions per CLAUDE.md: per-model privileges on Leads, Opportunities
  and Contracts, workflow privileges (Create Quotes, Confirm Sales Orders,
  Create Invoices, Send Contracts for Signature, Activate Contracts) and the
  CRM Administrator; standard roles ship in modern_crm_permission.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['mail', 'portal', 'utm', 'sale_management', 'account', 'hr'],
    'data': [
        'security/modern_crm_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/modern_crm_sequence.xml',
        'data/modern_crm_option_data.xml',
        'data/modern_crm_stage_data.xml',
        'data/modern_crm_contract_template_data.xml',
        'data/mail_template_data.xml',
        'data/modern_crm_cron.xml',
        'report/modern_crm_contract_report.xml',
        'views/modern_crm_option_views.xml',
        'views/modern_crm_stage_views.xml',
        'views/modern_crm_lead_views.xml',
        'views/modern_crm_opportunity_views.xml',
        'views/modern_crm_contract_views.xml',
        'views/modern_crm_contract_template_views.xml',
        'views/sale_order_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/modern_crm_portal_templates.xml',
        'wizard/modern_crm_lead_convert_views.xml',
        'wizard/modern_crm_reason_wizard_views.xml',
        'views/modern_crm_menus.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'modern_crm/static/src/scss/portal.scss',
        ],
    },
    'installable': True,
    'application': True,
}

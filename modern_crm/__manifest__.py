{
    'name': 'CRM',
    'version': '19.0.1.1.0',
    'category': 'Sales/CRM',
    'summary': 'Leads, opportunities, quotes and sales, modelled on Salesforce',
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
  opportunity's primary quote is the one Confirm Sale works on. Confirming
  a quote can mark the opportunity Closed Won. Confirm Sale
  turns the primary quote into a Sales Order and Create Invoice drafts the
  Invoice. With subscription_oca, modern_crm_subscription shows the
  Subscriptions those sales orders create.
* Permissions per CLAUDE.md: per-model privileges on Leads and
  Opportunities, workflow privileges (Create Quotes, Confirm Sales Orders,
  Create Invoices) and the CRM Administrator; standard roles ship in
  modern_crm_permission.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['mail', 'portal', 'utm', 'sale_management', 'account', 'hr'],
    'data': [
        'security/modern_crm_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/modern_crm_option_data.xml',
        'data/modern_crm_stage_data.xml',
        'views/modern_crm_option_views.xml',
        'views/modern_crm_stage_views.xml',
        'views/modern_crm_lead_views.xml',
        'views/modern_crm_opportunity_views.xml',
        'views/sale_order_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/modern_crm_portal_templates.xml',
        'wizard/modern_crm_lead_convert_views.xml',
        'wizard/modern_crm_reason_wizard_views.xml',
        'views/modern_crm_menus.xml',
    ],
    'installable': True,
    'application': True,
}

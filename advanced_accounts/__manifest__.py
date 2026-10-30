{
    'name': 'Advanced Accounts',
    'version': '19.0.1.0.1',
    'category': 'Sales/CRM',
    'summary': 'Accounts and Contacts, modelled on Salesforce and HubSpot, in place of the Contacts app',
    'description': """
Advanced Accounts (advanced_accounts)
=====================================
Two models take over from the standard Contacts app:

* Accounts: the companies and organisations you do business with (type,
  industry, owner, address, tags, notes), with their Contacts.
* Contacts: the people you deal with, each linked to an Account (or none).
  When a Contact needs to log in, "Create User" gives it a portal user built
  on the same partner, so the Contact and the user stay in sync.

Both keep their details on a res.partner, so invoices, emails, the portal and
every app still working with partners keep working. On install, every
outside company becomes an Account and every person a Contact (our own users,
employees and companies are left out); partners made later by other apps
(website, Point of Sale, lead conversion, ...) join automatically when they
are used on a record that has Accounts and Contacts.

The Contacts app's menu is hidden while this app is installed; the Contacts
module itself stays installed for the apps that use it.

Support apps (switched on in Settings > Advanced Accounts) put an Account
and a Contact field in place of the customer or vendor field in CRM, Sales,
Invoicing, Project, Helpdesk, Feature Suggestions, Print Farm Jobs,
Embroidery Jobs, Checklists, Sign'r, Purchase, Expenses, Point of Sale and
Asset Management. Picking an Account narrows the Contacts to that Account;
picking a Contact fills in its Account. Contact pickers list "Contact Name
(Account Name)"; the chosen Contact shows its name only.

Employees come from Personnel (advanced_hr): our employees and users are
never Contacts, and the "My Team" permissions follow Personnel's org chart.

Permissions per CLAUDE.md: per-model privileges on Accounts and Contacts, a
Create Users workflow privilege and the Advanced Accounts Administrator;
standard roles ship in advanced_accounts_permission.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['mail', 'base_setup', 'advanced_hr'],
    'data': [
        'security/advanced_accounts_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/advanced_account_type_data.xml',
        'views/advanced_account_views.xml',
        'views/advanced_contact_views.xml',
        'views/res_config_settings_views.xml',
        'views/advanced_accounts_menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
}

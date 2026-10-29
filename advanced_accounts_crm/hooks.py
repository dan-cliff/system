def uninstall_hook(env):
    # Point CRM's Customers menus back at its own partner lists.
    for menu, action in (('menu_modern_crm_accounts', 'modern_crm_account_action'),
                         ('menu_modern_crm_contacts', 'modern_crm_contact_action')):
        menu = env.ref(f'modern_crm.{menu}', raise_if_not_found=False)
        action = env.ref(f'modern_crm.{action}', raise_if_not_found=False)
        if menu and action:
            menu.action = action

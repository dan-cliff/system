def post_init_hook(env):
    """Take over from the Contacts app: every customer, vendor and other
    outside company gets an Account and every person a Contact (under their
    company's Account). Our own users, employees and companies are left out."""
    partners = env['res.partner'].search([])
    for start in range(0, len(partners), 1000):
        env['advanced.contact']._adopt_partners(partners[start:start + 1000])

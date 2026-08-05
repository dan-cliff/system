def _set_default_home_action(env):
    action = env.ref('web_home_menu.action_home_screen', raise_if_not_found=False)
    if not action:
        return
    users_without_home_action = env['res.users'].search([('action_id', '=', False)])
    users_without_home_action.write({'action_id': action.id})

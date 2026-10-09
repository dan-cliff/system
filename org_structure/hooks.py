def post_init_hook(env):
    env['res.users.org.scope']._sync_app_lines()

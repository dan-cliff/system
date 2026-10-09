def post_init_hook(env):
    # The Organisation tables exist now: rebuild the models so primary
    # models get their Organisation fields straight away.
    env.flush_all()
    env.registry._org_primary_models = None
    env.registry._org_parent_fields = None
    env.registry._setup_models__(env.cr)
    env['res.users.org.scope']._sync_app_lines()

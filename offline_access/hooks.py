def post_init_hook(env):
    """Start with the suggested Offline Models for the apps already installed."""
    env['offline.access.model'].action_add_suggested()

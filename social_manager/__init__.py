from . import controllers
from . import models
from . import wizard


def uninstall_hook(env):
    """Remove the per Platform / Page permissions (and their roles), which have no XML IDs."""
    env['social.platform'].with_context(active_test=False).search([])._social_access_remove()
    env['social.channel'].with_context(active_test=False).search([])._social_access_remove()

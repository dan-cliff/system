# -*- coding: utf-8 -*-
"""
post_init_hook for report_builder:

1. Seeds the Report Builder roles into the Permission Management role library.
2. Creates (or updates) a 'System Administrator' permission profile that holds
   the Report Builder – Manager role.
3. Assigns the built-in admin user to that profile if they do not already have
   a permission profile set.

All steps are no-ops if permission_management is not installed.
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    _seed_permission_roles(env)
    _setup_admin_profile(env)


def _seed_permission_roles(env):
    """Call _load_role_library() so the two Report Builder roles are created."""
    Role = env.get('permission.role')
    if Role is None:
        _logger.info(
            'report_builder post_init_hook: permission.role model not found — '
            'skipping role library seed.'
        )
        return
    try:
        Role._load_role_library()
        _logger.info('report_builder post_init_hook: role library seeded.')
    except Exception:
        _logger.exception(
            'report_builder post_init_hook: error calling _load_role_library.'
        )


def _setup_admin_profile(env):
    """
    Find the Report Builder – Manager role and ensure it is present in a
    'System Administrator' permission profile.  If the admin user has no
    profile assigned, assign this one.
    """
    Role = env.get('permission.role')
    Profile = env.get('permission.profile')
    if Role is None or Profile is None:
        return

    # Locate the Report Builder – Manager role
    privilege = env.ref('report_builder.privilege_report_builder', raise_if_not_found=False)
    manager_group = env.ref('report_builder.group_report_builder_manager', raise_if_not_found=False)
    if not privilege or not manager_group:
        _logger.warning(
            'report_builder post_init_hook: could not resolve privilege or '
            'manager group XML refs — skipping admin profile setup.'
        )
        return

    manager_role = Role.search([
        ('line_ids.privilege_id', '=', privilege.id),
        ('line_ids.group_id', '=', manager_group.id),
    ], limit=1)

    if not manager_role:
        _logger.warning(
            'report_builder post_init_hook: Report Builder – Manager role not '
            'found in library after seeding — skipping admin profile setup.'
        )
        return

    # Create or find the System Administrator profile
    admin_profile = Profile.search([('name', '=', 'System Administrator')], limit=1)
    if not admin_profile:
        admin_profile = Profile.create({
            'name': 'System Administrator',
            'description': (
                'Full system access across all applications. '
                'Automatically maintained — includes all administrator-level roles.'
            ),
            'role_ids': [(4, manager_role.id)],
        })
        _logger.info(
            'report_builder post_init_hook: created "System Administrator" '
            'permission profile (id=%d).', admin_profile.id
        )
    else:
        if manager_role.id not in admin_profile.role_ids.ids:
            admin_profile.write({'role_ids': [(4, manager_role.id)]})
            _logger.info(
                'report_builder post_init_hook: added Report Builder – Manager '
                'role to existing "System Administrator" profile.'
            )

    # Assign admin user to this profile if they have none yet
    admin_user = env.ref('base.user_admin', raise_if_not_found=False)
    if admin_user and not admin_user.sudo().permission_profile_id:
        admin_user.sudo().with_context(auto_profile_sync=True).write({
            'permission_profile_id': admin_profile.id,
        })
        admin_user.sudo()._sync_profile_groups()
        _logger.info(
            'report_builder post_init_hook: assigned "System Administrator" '
            'profile to admin user (id=%d).', admin_user.id
        )

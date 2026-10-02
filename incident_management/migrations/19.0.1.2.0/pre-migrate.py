"""Before the new access levels load, remove the old groups from Permission Management
roles: roles left empty are deleted, except those named like one of this app's new roles,
which are refilled with the new groups (keeping their profiles)."""
from odoo.addons.permission_management.access_levels_lib import pre_migrate_old_groups
from odoo.addons.incident_management import access_levels

OLD_GROUPS = [
    'incident_management.group_incident_admin',
    'incident_management.group_incident_manager',
    'incident_management.group_incident_user',
]


def migrate(cr, version):
    # The Confidential Bypass group stays, moving to the Incident Reports privilege.
    pre_migrate_old_groups(
        cr, access_levels, OLD_GROUPS,
        release_xmlids=['incident_management.group_incident_confidential_bypass'],
    )

"""Advanced Timesheets no longer needs Project: entries are grouped on the grid by Work Type,
and Project / Task moved to advanced_timesheet_project.

- Every project used on a timesheet entry becomes a Work Type of the same name, set on its
  entries, so their hours keep their rows if Project is uninstalled later.
- When Project is installed, advanced_timesheet_project is installed in this same upgrade,
  taking over the Project and Task fields so their values are kept."""
from odoo import SUPERUSER_ID, api


def _project_name(name):
    if isinstance(name, dict):
        return name.get('en_US') or next(iter(name.values()), '')
    return name or ''


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'advanced_timesheet_line' AND column_name = 'project_id'
    """)
    has_project_column = bool(cr.fetchone())
    cr.execute("SELECT to_regclass('project_project')")
    if has_project_column and cr.fetchone()[0]:
        cr.execute("""
            SELECT DISTINCT p.id, p.name
              FROM advanced_timesheet_line l
              JOIN project_project p ON p.id = l.project_id
             WHERE l.work_type_id IS NULL
        """)
        WorkType = env['advanced.timesheet.work.type'].with_context(active_test=False)
        for project_id, name in cr.fetchall():
            name = _project_name(name).strip() or 'Project %s' % project_id
            work_type = WorkType.search([('name', '=', name)], limit=1) or WorkType.create({'name': name})
            cr.execute(
                'UPDATE advanced_timesheet_line SET work_type_id = %s '
                'WHERE project_id = %s AND work_type_id IS NULL',
                (work_type.id, project_id),
            )

    bridge = env['ir.module.module'].search([
        ('name', '=', 'advanced_timesheet_project'), ('state', '=', 'uninstalled'),
    ])
    project = env['ir.module.module'].search([('name', '=', 'project'), ('state', '=', 'installed')])
    if bridge and project:
        bridge.button_install()

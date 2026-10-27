def migrate(cr, version):
    # The Overview was removed (Custom Dashboards are used instead): drop its
    # widgets' tables, which Odoo leaves behind when a model goes away.
    for table in (
        'advanced_project_overview_widget_advanced_project_phase_rel',
        'advanced_project_overview_widget_res_users_rel',
        'advanced_project_overview_widget',
    ):
        cr.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')

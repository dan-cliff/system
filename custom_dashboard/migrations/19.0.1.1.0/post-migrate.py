def migrate(cr, version):
    """Widgets that already had a colour keep it as their custom colour."""
    cr.execute(
        "UPDATE custom_dashboard_widget SET custom_colors = TRUE "
        "WHERE color IS NOT NULL AND color != ''"
    )

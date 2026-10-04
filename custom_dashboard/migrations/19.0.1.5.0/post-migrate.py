def migrate(cr, version):
    """Charts and tables now sort with Sort Groups By, like pivot tables. Carry over the
    old Sort's Largest / Smallest first; its Group order matches the default Sequence."""
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'custom_dashboard_widget' AND column_name = 'sort'"
    )
    if not cr.fetchone():
        return
    cr.execute(
        "UPDATE custom_dashboard_widget w SET pivot_row_sort = w.sort "
        "FROM custom_dashboard_widget_type t "
        "WHERE t.id = w.type_id AND t.code != 'pivot' AND w.sort IN ('value_desc', 'value_asc')"
    )
    cr.execute("ALTER TABLE custom_dashboard_widget DROP COLUMN sort")

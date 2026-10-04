"""Starting At (activity_start) is required on Risk Assessments and Risk Templates. Add the
column before the module's fields load and fill it for existing records (from the
assessment Date, or the template's creation time) so the NOT NULL constraint can be set."""


def migrate(cr, version):
    for table, source in (
        ('risk_assessment', 'date::timestamp'),
        ('risk_template', 'create_date'),
    ):
        cr.execute('ALTER TABLE %s ADD COLUMN IF NOT EXISTS activity_start timestamp' % table)
        cr.execute(
            'UPDATE %s SET activity_start = COALESCE(%s, now() at time zone \'UTC\') '
            'WHERE activity_start IS NULL' % (table, source)
        )

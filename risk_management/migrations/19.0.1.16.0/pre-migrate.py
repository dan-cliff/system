"""Starting At (activity_start) is required on Risk Assessments. Add the column before the
module's fields load and fill it from the assessment Date for existing records so the
NOT NULL constraint can be set."""


def migrate(cr, version):
    cr.execute('ALTER TABLE risk_assessment ADD COLUMN IF NOT EXISTS activity_start timestamp')
    cr.execute(
        "UPDATE risk_assessment SET activity_start = COALESCE(date::timestamp, now() at time zone 'UTC') "
        'WHERE activity_start IS NULL'
    )

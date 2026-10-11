"""The bowtie's separate Hazard field is gone: the risk's Unwanted Event is now the Hazard.

Keep any Hazard text already entered by moving it into the Unwanted Event before
the bowtie_hazard column is dropped (appended when both were filled in).
"""


def migrate(cr, version):
    for table in ('risk_assessment_line', 'risk_template_line'):
        cr.execute(
            """
            SELECT 1 FROM information_schema.columns
             WHERE table_name = %s AND column_name = 'bowtie_hazard'
            """,
            [table],
        )
        if not cr.fetchone():
            continue
        cr.execute(
            f"""
            UPDATE {table}
               SET unwanted_event = CASE
                       WHEN COALESCE(TRIM(unwanted_event), '') = '' THEN bowtie_hazard
                       ELSE unwanted_event || E'\\n\\n' || bowtie_hazard
                   END
             WHERE COALESCE(TRIM(bowtie_hazard), '') != ''
               AND COALESCE(unwanted_event, '') != bowtie_hazard
            """
        )

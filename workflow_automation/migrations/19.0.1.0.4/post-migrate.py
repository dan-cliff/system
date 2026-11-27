def migrate(cr, version):
    # Template emails used to ignore Send To and always go to the template's
    # own recipients: keep that for existing steps.
    cr.execute("""
        UPDATE wf_step
           SET email_to_type = 'template'
         WHERE email_type = 'template'
    """)

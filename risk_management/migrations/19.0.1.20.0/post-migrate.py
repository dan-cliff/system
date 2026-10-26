"""Turn the To-Dos saved by pre-migrate into Risk Assessment Actions, then drop the copy
and the old To-Do link table."""
import json

from odoo.tools import html2plaintext


def migrate(cr, version):
    cr.execute('DROP TABLE IF EXISTS risk_assessment_line_task_rel')
    cr.execute("DELETE FROM ir_model_relation WHERE name = 'risk_assessment_line_task_rel'")
    cr.execute("SELECT to_regclass('risk_action_task_migration')")
    if not cr.fetchone()[0]:
        return
    cr.execute("""
        SELECT m.line_id, m.name, m.description, m.date_deadline, m.task_state, m.user_id,
               m.create_uid, m.create_date, m.write_uid, m.write_date,
               l.assessment_id, a.company_id
          FROM risk_action_task_migration m
          JOIN risk_assessment_line l ON l.id = m.line_id
          JOIN risk_assessment a ON a.id = l.assessment_id
      ORDER BY m.line_id, m.task_id
    """)
    for (line_id, name, description, deadline, task_state, user_id,
         create_uid, create_date, write_uid, write_date, assessment_id, company_id) in cr.fetchall():
        # project.task name may be stored as text or as a translated jsonb value.
        if name and name.startswith('{'):
            try:
                values = json.loads(name)
                name = values.get('en_US') or next(iter(values.values()), '')
            except ValueError:
                pass
        state = {'1_done': 'done', '1_canceled': 'cancelled'}.get(task_state, 'open')
        cr.execute("""
            INSERT INTO risk_assessment_action
                (line_id, assessment_id, company_id, sequence, name, description, user_id,
                 date_deadline, state, create_uid, create_date, write_uid, write_date)
            VALUES (%s, %s, %s, 10, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (line_id, assessment_id, company_id, name or 'Action',
              html2plaintext(description) if description else None, user_id,
              deadline, state, create_uid, create_date, write_uid, write_date))
    cr.execute('DROP TABLE risk_action_task_migration')

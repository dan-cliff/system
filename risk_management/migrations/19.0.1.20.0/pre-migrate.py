"""Actions on Risk Assessment risks were To-Dos (project.task, from the Project app) linked
through risk_assessment_line_task_rel. They are now risk.assessment.action records, so the
module no longer needs Project. Keep a copy of the linked To-Dos before the old field goes;
post-migrate turns them into Actions."""


def migrate(cr, version):
    cr.execute("SELECT to_regclass('risk_assessment_line_task_rel'), to_regclass('project_task')")
    rel, task = cr.fetchone()
    if not (rel and task):
        return
    cr.execute('DROP TABLE IF EXISTS risk_action_task_migration')
    cr.execute("""
        CREATE TABLE risk_action_task_migration AS
        SELECT rel.line_id,
               t.id AS task_id,
               t.name::text AS name,
               t.description::text AS description,
               t.date_deadline::date AS date_deadline,
               t.state AS task_state,
               t.create_uid, t.create_date, t.write_uid, t.write_date,
               (SELECT MIN(u.user_id) FROM project_task_user_rel u WHERE u.task_id = t.id) AS user_id
          FROM risk_assessment_line_task_rel rel
          JOIN project_task t ON t.id = rel.task_id
          JOIN risk_assessment_line l ON l.id = rel.line_id
    """)

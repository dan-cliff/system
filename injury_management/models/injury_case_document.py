from odoo import fields, models, tools


class InjuryCaseDocument(models.Model):
    """Read-only SQL view that aggregates all attachments across all RTW Case
    sub-registers into a single list, preserving the source register and
    record context for each file.

    Security: access is granted at the model level via ir.model.access.csv
    (read-only, injury group members only).  Since all sub-register records
    share the same group-level security as the parent RTW Case, any user who
    can view a case automatically has access to its documents here.  If
    row-level rules are added to sub-register models in the future, update
    the corresponding ir.rule on this model accordingly.
    """

    _name = 'injury.case.document'
    _description = 'RTW Case Document'
    _auto = False
    _order = 'source_order, name'

    case_id = fields.Many2one('injury.rtw.case', string='RTW Case', readonly=True)
    attachment_id = fields.Many2one('ir.attachment', string='Attachment', readonly=True)
    source_register = fields.Char('Register', readonly=True)
    source_record_name = fields.Char('Source Record', readonly=True)
    source_order = fields.Integer(readonly=True)
    name = fields.Char('File Name', readonly=True)
    mimetype = fields.Char('File Type', readonly=True)
    file_size = fields.Integer('Size (bytes)', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW injury_case_document AS (
                SELECT
                    row_number() OVER (
                        ORDER BY sub.case_id, sub.source_order, sub.attachment_id
                    )::integer AS id,
                    sub.case_id,
                    sub.attachment_id,
                    sub.source_register,
                    sub.source_record_name,
                    sub.source_order,
                    a.name,
                    a.mimetype,
                    COALESCE(a.file_size, 0) AS file_size
                FROM (
                    SELECT cn.case_id, rel.attachment_id,
                           'Case Note'::text AS source_register,
                           1 AS source_order,
                           TO_CHAR(cn.note_date, 'DD Mon YYYY') AS source_record_name
                    FROM injury_case_note_ir_attachment_rel rel
                    JOIN injury_case_note cn ON cn.id = rel.note_id

                    UNION ALL

                    SELECT ma.case_id, rel.attachment_id,
                           'Medical Appointment'::text AS source_register,
                           2 AS source_order,
                           TO_CHAR(ma.appointment_date AT TIME ZONE 'UTC',
                                   'DD Mon YYYY') AS source_record_name
                    FROM injury_medical_appointment_ir_attachment_rel rel
                    JOIN injury_medical_appointment ma ON ma.id = rel.appointment_id

                    UNION ALL

                    SELECT im.case_id, rel.attachment_id,
                           'Meeting / Communication'::text AS source_register,
                           3 AS source_order,
                           im.subject AS source_record_name
                    FROM injury_meeting_ir_attachment_rel rel
                    JOIN injury_meeting im ON im.id = rel.meeting_id

                    UNION ALL

                    SELECT fn.case_id, rel.attachment_id,
                           'File Note'::text AS source_register,
                           4 AS source_order,
                           fn.subject AS source_record_name
                    FROM injury_file_note_ir_attachment_rel rel
                    JOIN injury_file_note fn ON fn.id = rel.file_note_id

                    UNION ALL

                    SELECT ic.case_id, rel.attachment_id,
                           'Cost'::text AS source_register,
                           5 AS source_order,
                           ic.description AS source_record_name
                    FROM injury_cost_ir_attachment_rel rel
                    JOIN injury_cost ic ON ic.id = rel.cost_id

                    UNION ALL

                    SELECT rp.case_id, rel.attachment_id,
                           'RTW Plan'::text AS source_register,
                           6 AS source_order,
                           rp.version AS source_record_name
                    FROM injury_rtw_plan_ir_attachment_rel rel
                    JOIN injury_rtw_plan rp ON rp.id = rel.plan_id

                    UNION ALL

                    SELECT mc.case_id, rel.attachment_id,
                           'Medical Certificate'::text AS source_register,
                           7 AS source_order,
                           mc.doctor_name AS source_record_name
                    FROM injury_medical_certificate_ir_attachment_rel rel
                    JOIN injury_medical_certificate mc ON mc.id = rel.certificate_id
                ) sub
                JOIN ir_attachment a ON a.id = sub.attachment_id
            )
        """)

    def action_download(self):
        """Download the underlying file."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self.attachment_id.id}?download=true',
            'target': 'new',
        }

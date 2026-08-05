import io
import base64
from odoo import api, fields, models
from odoo.tools.pdf import PdfFileReader, PdfFileWriter


class InjuryCaseReportWizard(models.TransientModel):
    """Wizard to build a selective PDF export of an RTW Case.

    The user chooses which registers to include; the selected sections are
    rendered as pages in the generated PDF.  Optionally the linked Incident
    Report can be appended as an addendum by merging both PDFs server-side.
    """

    _name = 'injury.case.report.wizard'
    _description = 'RTW Case PDF Export Wizard'

    case_id = fields.Many2one(
        'injury.rtw.case', string='RTW Case',
        required=True, ondelete='cascade')

    include_case_notes = fields.Boolean('Case Notes', default=True)
    include_appointments = fields.Boolean('Medical Appointments', default=True)
    include_meetings = fields.Boolean('Meetings & Communications', default=True)
    include_file_notes = fields.Boolean('File Notes', default=True)
    include_costs = fields.Boolean('Costs', default=True)
    include_rtw_plans = fields.Boolean('RTW Plans', default=True)
    include_certificates = fields.Boolean('Medical Certificates', default=True)

    # Addendum option — only relevant when a linked incident exists
    include_incident_report = fields.Boolean(
        'Incident Report Addendum', default=False)
    has_incident_report = fields.Boolean(
        compute='_compute_has_incident_report', store=False)

    # Which sections to include in the appended incident report
    inc_report_details = fields.Boolean('Report Details', default=True)
    inc_investigation = fields.Boolean('Investigation & ICAM Findings', default=True)
    inc_corrective_actions = fields.Boolean('Corrective Actions', default=True)

    # Availability hints (read-only, shown in view to guide the user)
    case_note_count = fields.Integer(related='case_id.case_note_count')
    appointment_count = fields.Integer(related='case_id.appointment_count')
    meeting_count = fields.Integer(related='case_id.meeting_count')
    file_note_count = fields.Integer(related='case_id.file_note_count')
    cost_count = fields.Integer(related='case_id.cost_count')
    rtw_plan_count = fields.Integer(related='case_id.rtw_plan_count')
    certificate_count = fields.Integer(related='case_id.certificate_count')

    @api.depends('case_id.incident_id')
    def _compute_has_incident_report(self):
        for w in self:
            w.has_incident_report = bool(w.case_id.incident_id)

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_print(self):
        """Generate the PDF report, optionally merging the linked incident PDF."""
        self.ensure_one()

        rtw_action = self.env.ref('injury_management.action_report_injury_case_full')

        if not (self.include_incident_report and self.case_id.incident_id):
            # Simple path — RTW case PDF only
            return rtw_action.report_action(self)

        # ── Merged path: RTW case + Incident Report addendum ─────────────────

        # 1. Generate RTW case PDF
        rtw_pdf, _ = rtw_action._render_qweb_pdf(
            rtw_action.report_name, [self.id])

        # 2. Generate Incident Report PDF via a temporary wizard record
        incident_wizard = self.env['incident.report.wizard'].create({
            'incident_id': self.case_id.incident_id.id,
            'include_report': self.inc_report_details,
            'include_investigation': self.inc_investigation,
            'include_corrective_actions': self.inc_corrective_actions,
        })
        inc_action = self.env.ref('incident_management.action_report_incident_full')
        inc_pdf, _ = inc_action._render_qweb_pdf(
            inc_action.report_name, [incident_wizard.id])

        # 3. Merge both PDFs
        writer = PdfFileWriter()
        for pdf_bytes in (rtw_pdf, inc_pdf):
            reader = PdfFileReader(io.BytesIO(pdf_bytes))
            for page in range(reader.getNumPages()):
                writer.addPage(reader.getPage(page))

        merged_buf = io.BytesIO()
        writer.write(merged_buf)

        # 4. Store as a temporary attachment and return a download URL
        filename = 'RTW Case Report - %s.pdf' % self.case_id.name
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(merged_buf.getvalue()),
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'self',
        }

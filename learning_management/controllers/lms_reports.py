import io
import json
import logging
from datetime import date, timedelta

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class LmsReportsController(http.Controller):
    """Backend HTTP endpoints for LMS report exports."""

    @http.route(
        '/learning/tna/pdf',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def tna_pdf(self, domain='[]', **kwargs):
        """
        Generate a landscape A4 PDF of the Training Needs Analysis matrix.

        Query parameters
        ----------------
        domain : str
            JSON-encoded Odoo domain list, e.g.
            ``[["course_type","=","licence"]]``
        """
        try:
            parsed_domain = json.loads(domain)
        except (ValueError, TypeError):
            parsed_domain = []

        report_sudo = request.env['ir.actions.report'].sudo()
        pdf_content, _content_type = report_sudo._render_qweb_pdf(
            'learning_management.action_lms_tna_pdf',
            [],
            data={'domain': parsed_domain},
        )

        return request.make_response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition',
                 'attachment; filename="training_needs_analysis.pdf"'),
            ],
        )

    # ── TNA Excel ─────────────────────────────────────────────────────────────

    @http.route(
        '/learning/tna/excel',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def tna_excel(self, domain='[]', **kwargs):
        """Export the TNA matrix as an .xlsx workbook."""
        try:
            parsed_domain = json.loads(domain)
        except (ValueError, TypeError):
            parsed_domain = []

        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        matrix = request.env['lms.employee.record'].sudo().get_tna_matrix_data(parsed_domain)
        employees = matrix['employees']
        courses   = matrix['courses']
        cells     = matrix['cells']

        STATE_LABELS = {
            'completed':            'Completed',
            'in_progress':          'In Progress',
            'not_started':          'Not Started',
            'pending_upload':       'Pending Upload',
            'pending_verification': 'Pending Verification',
            'failed':               'Failed',
            'expired':              'Expired',
            'lapsed':               'Lapsed',
        }
        STATE_FILLS = {
            'completed':            'C6EFCE',
            'in_progress':          'BDD7EE',
            'not_started':          'E9ECEF',
            'pending_upload':       'FFEB9C',
            'pending_verification': 'FFE699',
            'failed':               'FFC7CE',
            'expired':              'F5C6CB',
            'lapsed':               'E2D9F3',
        }
        thin = Side(style='thin', color='DEE2E6')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'TNA Matrix'

        header_fill = PatternFill('solid', fgColor='4472C4')
        header_font = Font(bold=True, color='FFFFFF', size=9)

        # Row 1: blank corner + employee names
        ws.cell(row=1, column=1, value='Course / Employee').font = header_font
        ws.cell(row=1, column=1).fill = header_fill
        ws.cell(row=1, column=1).border = border
        ws.cell(row=1, column=1).alignment = Alignment(wrap_text=True)

        for col_idx, emp in enumerate(employees, start=2):
            cell = ws.cell(row=1, column=col_idx, value=emp['name'])
            cell.font = header_font
            cell.fill = header_fill
            cell.border = border
            cell.alignment = Alignment(wrap_text=True, horizontal='center')

        # Course rows
        for row_idx, course in enumerate(courses, start=2):
            course_label = (course.get('code', '') + ' ' + course['name']).strip()
            c = ws.cell(row=row_idx, column=1, value=course_label)
            c.font = Font(size=8, bold=True)
            c.border = border
            c.alignment = Alignment(wrap_text=True)

            for col_idx, emp in enumerate(employees, start=2):
                key = f"{emp['id']}_{course['id']}"
                cell_data = cells.get(key)
                if cell_data:
                    state = cell_data['state']
                    label = STATE_LABELS.get(state, state)
                    exp   = cell_data.get('expiry_date') or ''
                    value = label + ('\n' + exp[8:10] + '/' + exp[5:7] + '/' + exp[:4] if exp else '')
                    fill_hex = STATE_FILLS.get(state, 'F8F9FA')
                else:
                    value = ''
                    fill_hex = 'F8F9FA'
                d = ws.cell(row=row_idx, column=col_idx, value=value)
                d.font = Font(size=8)
                d.fill = PatternFill('solid', fgColor=fill_hex)
                d.border = border
                d.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        # Column widths
        ws.column_dimensions[get_column_letter(1)].width = 28
        for col_idx in range(2, len(employees) + 2):
            ws.column_dimensions[get_column_letter(col_idx)].width = 14

        ws.row_dimensions[1].height = 40
        ws.freeze_panes = 'B2'

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        return request.make_response(
            buf.read(),
            headers=[
                ('Content-Type',
                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition',
                 'attachment; filename="training_needs_analysis.xlsx"'),
            ],
        )

    # ── Expiring PDF ──────────────────────────────────────────────────────────

    @http.route(
        '/learning/expiring/pdf',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def expiring_pdf(self, domain='[]', **kwargs):
        """Generate a portrait A4 PDF of the Training Records Expiring list."""
        try:
            parsed_domain = json.loads(domain)
        except (ValueError, TypeError):
            parsed_domain = []

        report_sudo = request.env['ir.actions.report'].sudo()
        pdf_content, _content_type = report_sudo._render_qweb_pdf(
            'learning_management.action_lms_expiring_pdf',
            [],
            data={'domain': parsed_domain},
        )

        return request.make_response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition',
                 'attachment; filename="training_records_expiring.pdf"'),
            ],
        )

    # ── Expiring Excel ────────────────────────────────────────────────────────

    @http.route(
        '/learning/expiring/excel',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def expiring_excel(self, domain='[]', **kwargs):
        """Export the Training Records Expiring list as an .xlsx workbook."""
        try:
            parsed_domain = json.loads(domain)
        except (ValueError, TypeError):
            parsed_domain = []

        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        records = request.env['lms.employee.record'].sudo().get_expiring_report_data(parsed_domain)
        today = date.today()

        thin = Side(style='thin', color='DEE2E6')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Training Records Expiring'

        headers = [
            'Employee', 'Department', 'Company', 'Course', 'Code',
            'Type', 'Status', 'Started On', 'Completed On', 'Expires On',
        ]
        header_fill = PatternFill('solid', fgColor='4472C4')
        header_font = Font(bold=True, color='FFFFFF', size=9)

        for col_idx, h in enumerate(headers, start=1):
            c = ws.cell(row=1, column=col_idx, value=h)
            c.font = header_font
            c.fill = header_fill
            c.border = border
            c.alignment = Alignment(horizontal='center')

        STATE_LABELS = {
            'completed':            'Completed',
            'in_progress':          'In Progress',
            'not_started':          'Not Started',
            'pending_upload':       'Pending Upload',
            'pending_verification': 'Pending Verification',
            'failed':               'Failed',
            'expired':              'Expired',
            'lapsed':               'Lapsed',
        }

        for row_idx, rec in enumerate(records, start=2):
            alt = (row_idx % 2 == 0)
            row_fill = PatternFill('solid', fgColor='F2F2F2') if alt else PatternFill('solid', fgColor='FFFFFF')

            def _fmt_iso(d):
                if not d:
                    return ''
                return d[8:10] + '/' + d[5:7] + '/' + d[:4]

            expiry_iso = rec.get('expiry_date') or ''
            expiry_fill = row_fill
            if expiry_iso:
                exp_date = date.fromisoformat(expiry_iso)
                delta = (exp_date - today).days
                if delta < 0:
                    expiry_fill = PatternFill('solid', fgColor='FFC7CE')
                elif delta <= 30:
                    expiry_fill = PatternFill('solid', fgColor='FFEB9C')
                elif delta <= 90:
                    expiry_fill = PatternFill('solid', fgColor='FFEB99')
                else:
                    expiry_fill = PatternFill('solid', fgColor='C6EFCE')

            course_type_label = rec.get('course_type', '').replace('_', ' ').title()

            row_values = [
                rec['employee_name'],
                rec['department'],
                rec['company'],
                rec['course_name'],
                rec.get('course_code', ''),
                course_type_label,
                STATE_LABELS.get(rec['state'], rec['state']),
                _fmt_iso(rec.get('start_date')),
                _fmt_iso(rec.get('completion_date')),
                _fmt_iso(expiry_iso),
            ]

            for col_idx, value in enumerate(row_values, start=1):
                c = ws.cell(row=row_idx, column=col_idx, value=value)
                c.font = Font(size=9)
                c.fill = expiry_fill if col_idx == 10 else row_fill
                c.border = border
                c.alignment = Alignment(horizontal='left' if col_idx <= 7 else 'center')

        # Column widths
        col_widths = [22, 18, 16, 30, 10, 14, 18, 12, 12, 12]
        for col_idx, width in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        ws.freeze_panes = 'A2'

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        return request.make_response(
            buf.read(),
            headers=[
                ('Content-Type',
                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition',
                 'attachment; filename="training_records_expiring.xlsx"'),
            ],
        )

    # ── Sessions PDF ──────────────────────────────────────────────────────────

    @http.route(
        '/learning/sessions/pdf',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def sessions_pdf(self, domain='[]', **kwargs):
        """Generate a landscape A4 PDF of the Training Sessions report."""
        try:
            parsed_domain = json.loads(domain)
        except (ValueError, TypeError):
            parsed_domain = []

        report_sudo = request.env['ir.actions.report'].sudo()
        pdf_content, _content_type = report_sudo._render_qweb_pdf(
            'learning_management.action_lms_sessions_pdf',
            [],
            data={'domain': parsed_domain},
        )

        return request.make_response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition',
                 'attachment; filename="training_sessions.pdf"'),
            ],
        )

    # ── Sessions Excel ────────────────────────────────────────────────────────

    @http.route(
        '/learning/sessions/excel',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def sessions_excel(self, domain='[]', **kwargs):
        """Export the Training Sessions list as an .xlsx workbook."""
        try:
            parsed_domain = json.loads(domain)
        except (ValueError, TypeError):
            parsed_domain = []

        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        records = request.env['lms.course.session'].sudo().get_sessions_report_data(parsed_domain)
        today = date.today()

        STATE_FILLS = {
            'draft':       'E9ECEF',
            'open':        'BDD7EE',
            'full':        'FFD9B3',
            'closed':      'FFC7CE',
            'in_progress': 'BDD7EE',
            'completed':   'C6EFCE',
            'cancelled':   'FFC7CE',
        }
        STATE_LABELS = {
            'draft':       'Draft',
            'open':        'Open for Enrolment',
            'full':        'Full',
            'closed':      'Closed for Enrolment',
            'in_progress': 'In Progress',
            'completed':   'Completed',
            'cancelled':   'Cancelled',
        }

        thin = Side(style='thin', color='DEE2E6')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Training Sessions'

        headers = [
            'Session Name', 'Course', 'Start Date & Time', 'End Date & Time',
            'Location / Venue', 'Instructor / Facilitator', 'Status',
            'Max Capacity', 'Enrolled', 'Seats Available',
        ]
        header_fill = PatternFill('solid', fgColor='4472C4')
        header_font = Font(bold=True, color='FFFFFF', size=9)

        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = border
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        ws.row_dimensions[1].height = 22

        def fmt_dt(val):
            if not val:
                return ''
            return val[8:10] + '/' + val[5:7] + '/' + val[:4] + ' ' + val[11:16]

        for row_idx, rec in enumerate(records, start=2):
            row_fill = PatternFill('solid', fgColor='FFFFFF' if row_idx % 2 == 0 else 'F2F2F2')
            state_fill = PatternFill('solid', fgColor=STATE_FILLS.get(rec['state'], 'E9ECEF'))

            row_data = [
                rec['name'],
                rec['course_name'],
                fmt_dt(rec.get('date_start')),
                fmt_dt(rec.get('date_end')),
                rec['location'],
                rec['instructor'],
                STATE_LABELS.get(rec['state'], rec['state']),
                rec['max_capacity'],
                rec['enrolled_count'],
                rec['available_seats'],
            ]

            for col_idx, value in enumerate(row_data, start=1):
                is_state_col = col_idx == 7
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.font = Font(size=9)
                cell.fill = state_fill if is_state_col else row_fill
                cell.border = border
                cell.alignment = Alignment(
                    horizontal='center' if col_idx in (3, 4, 8, 9, 10) else 'left',
                    vertical='center',
                )

        col_widths = [28, 22, 18, 18, 22, 22, 18, 10, 10, 12]
        for col_idx, width in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        ws.freeze_panes = 'A2'

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        return request.make_response(
            buf.read(),
            headers=[
                ('Content-Type',
                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition',
                 'attachment; filename="training_sessions.xlsx"'),
            ],
        )

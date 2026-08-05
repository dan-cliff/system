from odoo import models, api

# Number of employee columns to render per landscape A4 page
_EMPLOYEES_PER_PAGE = 15

# Number of rows per portrait A4 page for the Expiring report
_PAGE_SIZE_EXP = 40

_STATE_LABELS = {
    'completed':            'Completed',
    'in_progress':          'In Progress',
    'not_started':          'Not Started',
    'pending_upload':       'Pending Upload',
    'pending_verification': 'Pending Verification',
    'failed':               'Failed',
    'expired':              'Expired',
    'lapsed':               'Lapsed',
}

# Inline cell background/text colours matching the OWL matrix CSS
_STATE_STYLES = {
    'completed':            'background:#d1e7dd;color:#0a3622;',
    'in_progress':          'background:#cfe2ff;color:#084298;',
    'not_started':          'background:#e9ecef;color:#6c757d;',
    'pending_upload':       'background:#fff3cd;color:#664d03;',
    'pending_verification': 'background:#ffe69c;color:#664d03;',
    'failed':               'background:#f8d7da;color:#58151c;',
    'expired':              'background:#f5c6cb;color:#842029;',
    'lapsed':               'background:#e2d9f3;color:#432874;',
    'none':                 'background:#f8f9fa;color:#adb5bd;',
}


class LmsTnaReportPdf(models.AbstractModel):
    _name = 'report.learning_management.lms_tna_report_pdf'
    _description = 'TNA Matrix PDF Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        domain = (data or {}).get('domain', [])
        matrix = self.env['lms.employee.record'].get_tna_matrix_data(domain)

        employees = matrix['employees']
        courses   = matrix['courses']
        cells     = matrix['cells']

        # Split employees into pages so each page fits landscape A4
        emp_pages = [
            employees[i:i + _EMPLOYEES_PER_PAGE]
            for i in range(0, max(len(employees), 1), _EMPLOYEES_PER_PAGE)
        ]

        return {
            'company':      self.env.company,
            'emp_pages':    emp_pages,
            'courses':      courses,
            'cells':        cells,
            'state_labels': _STATE_LABELS,
            'state_styles': _STATE_STYLES,
        }


_SESSION_STATE_LABELS = {
    'draft':       'Draft',
    'open':        'Open for Enrolment',
    'full':        'Full',
    'closed':      'Closed for Enrolment',
    'in_progress': 'In Progress',
    'completed':   'Completed',
    'cancelled':   'Cancelled',
}

_SESSION_STATE_STYLES = {
    'draft':       'background:#e9ecef;color:#6c757d;',
    'open':        'background:#cfe2ff;color:#084298;',
    'full':        'background:#ffe5d0;color:#7d3900;',
    'closed':      'background:#f8d7da;color:#58151c;',
    'in_progress': 'background:#cfe2ff;color:#084298;',
    'completed':   'background:#d1e7dd;color:#0a3622;',
    'cancelled':   'background:#f8d7da;color:#842029;',
}

# Rows per landscape A4 page for the Sessions report
_PAGE_SIZE_SES = 35


class LmsSessionsReportPdf(models.AbstractModel):
    _name = 'report.learning_management.lms_sessions_report_pdf'
    _description = 'Training Sessions PDF Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        domain = (data or {}).get('domain', [])
        records = self.env['lms.course.session'].get_sessions_report_data(domain)
        pages = [
            records[i:i + _PAGE_SIZE_SES]
            for i in range(0, max(len(records), 1), _PAGE_SIZE_SES)
        ]
        return {
            'company':       self.env.company,
            'pages':         pages,
            'state_labels':  _SESSION_STATE_LABELS,
            'state_styles':  _SESSION_STATE_STYLES,
        }


class LmsExpiringReportPdf(models.AbstractModel):
    _name = 'report.learning_management.lms_expiring_report_pdf'
    _description = 'Training Records Expiring PDF Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        domain = (data or {}).get('domain', [])
        records = self.env['lms.employee.record'].get_expiring_report_data(domain)
        pages = [
            records[i:i + _PAGE_SIZE_EXP]
            for i in range(0, max(len(records), 1), _PAGE_SIZE_EXP)
        ]
        return {
            'company':       self.env.company,
            'pages':         pages,
            'state_labels':  _STATE_LABELS,
            'state_styles':  _STATE_STYLES,
        }

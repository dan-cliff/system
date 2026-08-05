# -*- coding: utf-8 -*-
import base64
import io
import json
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

PDF_PAGE_SIZES = [
    ('A4', 'A4'),
    ('A3', 'A3'),
    ('A2', 'A2'),
    ('A1', 'A1'),
    ('A0', 'A0'),
]

PDF_ORIENTATIONS = [
    ('portrait', 'Portrait'),
    ('landscape', 'Landscape'),
]

REPORT_FORMATS = [
    ('excel', 'Excel (.xlsx)'),
    ('csv', 'CSV (.csv)'),
    ('matrix', 'Matrix'),
    ('pdf', 'PDF'),
]


class ReportBuilder(models.Model):
    _name = 'report.builder'
    _description = 'Report Builder'
    _order = 'name'

    name = fields.Char(string='Report Name', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    # Model selection
    model_id = fields.Many2one(
        'ir.model', string='Primary Model', required=True,
        ondelete='cascade',
        domain=[('transient', '=', False)],
        help='The main model this report is based on.'
    )
    model_name = fields.Char(related='model_id.model', string='Model Technical Name', store=True)

    # Domain filtering
    domain = fields.Char(
        string='Filter Domain',
        default='[]',
        help='Standard Odoo domain expression to filter records.'
    )
    domain_description = fields.Text(
        string='Domain Description',
        help='Human-readable description of the filter conditions.'
    )

    # Column definitions
    column_ids = fields.One2many(
        'report.builder.column', 'report_id',
        string='Columns'
    )

    # Report format
    report_format = fields.Selection(
        REPORT_FORMATS, string='Report Format', required=True, default='excel'
    )

    # PDF-specific
    pdf_page_size = fields.Selection(
        PDF_PAGE_SIZES, string='Page Size', default='A4'
    )
    pdf_orientation = fields.Selection(
        PDF_ORIENTATIONS, string='Orientation', default='portrait'
    )

    # Matrix-specific
    matrix_row_field_id = fields.Many2one(
        'ir.model.fields', string='Row Axis Field',
        ondelete='set null',
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['many2one', 'char', 'selection'])]",
        help='Field used for the vertical (row) axis of the matrix.'
    )
    matrix_col_field_id = fields.Many2one(
        'ir.model.fields', string='Column Axis Field',
        ondelete='set null',
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['many2one', 'char', 'selection'])]",
        help='Field used for the horizontal (column) axis of the matrix.'
    )
    matrix_cell_field_id = fields.Many2one(
        'ir.model.fields', string='Cell Value Field',
        ondelete='set null',
        domain="[('model_id', '=', model_id)]",
        help='Field value displayed at the intersection of row and column.'
    )
    matrix_row_label = fields.Char(string='Row Axis Label', help='Label for the row dimension.')
    matrix_col_label = fields.Char(string='Column Axis Label', help='Label for the column dimension.')

    # Menu placement — parent menus selected by the user
    menu_ids = fields.Many2many(
        'ir.ui.menu', 'report_builder_menu_rel',
        'report_id', 'menu_id',
        string='Add to Menus',
        help='Select menus where this report will appear as an action.'
    )

    # Auto-created download action (shared across all menu placements)
    download_action_id = fields.Many2one(
        'ir.actions.act_url',
        string='Download Action',
        ondelete='set null',
        copy=False,
        readonly=True,
    )

    # Auto-created child menu items (one per selected parent menu)
    auto_menu_ids = fields.Many2many(
        'ir.ui.menu', 'report_builder_auto_menu_rel',
        'report_id', 'menu_id',
        string='Generated Menu Items',
        copy=False,
        readonly=True,
    )

    # Computed
    column_count = fields.Integer(
        string='Columns', compute='_compute_column_count', store=True
    )

    @api.depends('column_ids')
    def _compute_column_count(self):
        for rec in self:
            rec.column_count = len(rec.column_ids)

    @api.constrains('report_format', 'pdf_page_size', 'pdf_orientation')
    def _check_pdf_fields(self):
        for rec in self:
            if rec.report_format == 'pdf':
                if not rec.pdf_page_size:
                    raise ValidationError(_('Page size is required for PDF reports.'))
                if not rec.pdf_orientation:
                    raise ValidationError(_('Orientation is required for PDF reports.'))

    @api.constrains('report_format', 'matrix_row_field_id', 'matrix_col_field_id', 'matrix_cell_field_id')
    def _check_matrix_fields(self):
        for rec in self:
            if rec.report_format == 'matrix':
                if not rec.matrix_row_field_id:
                    raise ValidationError(_('Row axis field is required for Matrix reports.'))
                if not rec.matrix_col_field_id:
                    raise ValidationError(_('Column axis field is required for Matrix reports.'))
                if not rec.matrix_cell_field_id:
                    raise ValidationError(_('Cell value field is required for Matrix reports.'))

    # ------------------------------------------------------------------
    # ORM overrides — keep auto-created menus in sync
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_menus()
        return records

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get('_skip_menu_sync') and (
            'menu_ids' in vals or 'name' in vals
        ):
            self._sync_menus()
        return result

    def unlink(self):
        # Delete auto-created menus and actions before the report goes away
        self.sudo().auto_menu_ids.unlink()
        self.sudo().download_action_id.unlink()
        return super().unlink()

    def _sync_menus(self):
        """
        Create/update child ir.ui.menu entries so this report appears under
        every parent menu in menu_ids.  One ir.actions.act_url is shared
        across all placements; auto_menu_ids tracks the generated children
        so they can be cleaned up when the parent list changes.
        """
        for rec in self:
            # ── 1. Ensure a download action exists ──────────────────────
            url = '/report_builder/download/%d' % rec.id
            if rec.download_action_id:
                rec.download_action_id.sudo().write({
                    'name': rec.name,
                    'url': url,
                })
            else:
                action = rec.env['ir.actions.act_url'].sudo().create({
                    'name': rec.name,
                    'url': url,
                    'target': 'self',
                })
                # Write directly to avoid re-triggering _sync_menus
                rec.sudo().with_context(_skip_menu_sync=True).write(
                    {'download_action_id': action.id}
                )

            action_ref = 'ir.actions.act_url,%d' % rec.download_action_id.id

            # ── 2. Remove all previously auto-created child menus ───────
            rec.sudo().auto_menu_ids.unlink()

            # ── 3. Create one child menu per selected parent ─────────────
            new_menus = rec.env['ir.ui.menu']
            for parent in rec.menu_ids:
                child = rec.env['ir.ui.menu'].sudo().create({
                    'name': rec.name,
                    'parent_id': parent.id,
                    'action': action_ref,
                })
                new_menus |= child

            rec.sudo().with_context(_skip_menu_sync=True).write(
                {'auto_menu_ids': [(6, 0, new_menus.ids)]}
            )

    def action_run_report(self):
        """Trigger report generation - returns download action."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report_builder/download/%d' % self.id,
            'target': 'self',
        }

    def _get_records(self):
        """Fetch records based on model and domain."""
        self.ensure_one()
        try:
            domain = json.loads(self.domain or '[]')
        except (json.JSONDecodeError, ValueError):
            domain = []
        Model = self.env[self.model_name]
        return Model.search(domain)

    def _get_field_value(self, record, field_path):
        """
        Traverse a dotted field path (e.g. 'partner_id.country_id.name')
        and return a string representation of the value.
        """
        parts = field_path.split('.')
        value = record
        for part in parts:
            if not value:
                return ''
            if hasattr(value, part):
                value = getattr(value, part)
            else:
                return ''
        # Convert to string
        if isinstance(value, models.BaseModel):
            if len(value) == 0:
                return ''
            if len(value) == 1:
                return value.display_name or str(value.id)
            return ', '.join(v.display_name or str(v.id) for v in value)
        # bool must be checked before int because bool is a subclass of int
        if isinstance(value, bool):
            return 'Yes' if value else 'No'
        if value is None:
            return ''
        return str(value)

    def _get_column_headers(self):
        """Return list of column header labels in sequence order."""
        return [col.label or col.field_path for col in
                self.column_ids.sorted('sequence')]

    def _get_row_data(self, records):
        """Return list of rows, each row is a list of string values."""
        columns = self.column_ids.sorted('sequence')
        rows = []
        for record in records:
            row = [self._get_field_value(record, col.field_path) for col in columns]
            rows.append(row)
        return rows

    # ------------------------------------------------------------------
    # Excel generation  (xlsxwriter — produces clean OOXML natively)
    # ------------------------------------------------------------------
    def _generate_excel(self):
        """Generate a formatted .xlsx file and return (filename, bytes).

        Uses xlsxwriter (a write-only library) instead of openpyxl so that
        the output is clean OOXML with no post-processing required — the same
        philosophy as the CSV exporter which uses Python's built-in csv module
        and never needs to patch its own output.
        """
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(_('xlsxwriter is required for Excel export. Please install it.'))

        records = self._get_records()
        headers = self._get_column_headers()
        rows = self._get_row_data(records)

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        ws = wb.add_worksheet(self.name[:31])

        # ── Formats ─────────────────────────────────────────────────────────
        title_fmt = wb.add_format({
            'bold': True, 'font_size': 14,
            'font_color': '#FFFFFF', 'bg_color': '#2C5F8A',
            'align': 'left', 'valign': 'vcenter',
        })
        meta_fmt = wb.add_format({
            'italic': True, 'font_size': 10, 'font_color': '#555555',
            'align': 'left', 'valign': 'vcenter',
        })
        header_fmt = wb.add_format({
            'bold': True, 'font_size': 11,
            'font_color': '#FFFFFF', 'bg_color': '#1F4E79',
            'align': 'center', 'valign': 'vcenter',
            'text_wrap': True, 'border': 1,
        })
        data_fmt = wb.add_format({
            'font_size': 10, 'valign': 'vcenter', 'border': 1,
        })
        data_alt_fmt = wb.add_format({
            'font_size': 10, 'valign': 'vcenter', 'border': 1,
            'bg_color': '#EBF2FA',
        })

        num_cols = max(len(headers), 1)
        col_widths = [10] * num_cols
        r = 0  # 0-based row index

        def _write_merged(row_idx, text, fmt, height):
            """Write a full-width row, merging across all columns when there are 2+."""
            if num_cols > 1:
                ws.merge_range(row_idx, 0, row_idx, num_cols - 1, text, fmt)
            else:
                ws.write(row_idx, 0, text, fmt)
            ws.set_row(row_idx, height)

        # ── Title ────────────────────────────────────────────────────────────
        _write_merged(r, self.name, title_fmt, 28)
        r += 1

        # ── Model ────────────────────────────────────────────────────────────
        _write_merged(r, 'Model: %s' % self.model_id.name, meta_fmt, 16)
        r += 1

        # ── Domain description ───────────────────────────────────────────────
        domain_text = self.domain_description or ('Filter: %s' % (self.domain or 'None'))
        _write_merged(r, domain_text, meta_fmt, 16)
        r += 1

        # ── Record count ─────────────────────────────────────────────────────
        _write_merged(r, 'Records: %d' % len(records), meta_fmt, 14)
        r += 1

        # ── Blank separator row ──────────────────────────────────────────────
        ws.set_row(r, 6)
        r += 1

        # ── Column headers ───────────────────────────────────────────────────
        for c, header in enumerate(headers):
            ws.write(r, c, header, header_fmt)
            col_widths[c] = max(col_widths[c], len(str(header)) + 2)
        ws.set_row(r, 22)
        r += 1

        # ── Data rows ────────────────────────────────────────────────────────
        for row_idx, data_row in enumerate(rows):
            fmt = data_alt_fmt if row_idx % 2 == 1 else data_fmt
            for c, value in enumerate(data_row):
                ws.write(r, c, value or '', fmt)
                if c < num_cols:
                    col_widths[c] = max(col_widths[c], len(str(value or '')) + 2)
            ws.set_row(r, 16)
            r += 1

        # ── Column widths ────────────────────────────────────────────────────
        for c, w in enumerate(col_widths):
            ws.set_column(c, c, min(w, 60))

        # ── Freeze: lock the 4 meta rows + blank separator + header (rows 0–5) ──
        ws.freeze_panes(6, 0)

        wb.close()
        buf.seek(0)
        filename = '%s.xlsx' % self.name.replace('/', '-')
        return filename, buf.read()

    # ------------------------------------------------------------------
    # CSV generation
    # ------------------------------------------------------------------
    def _generate_csv(self):
        """Generate a .csv file and return (filename, bytes)."""
        import csv

        records = self._get_records()
        headers = self._get_column_headers()
        rows = self._get_row_data(records)

        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
        writer.writerow(headers)
        writer.writerows(rows)

        filename = '%s.csv' % self.name.replace('/', '-')
        return filename, buf.getvalue().encode('utf-8-sig')

    # ------------------------------------------------------------------
    # Matrix generation  (xlsxwriter — produces clean OOXML natively)
    # ------------------------------------------------------------------
    def _generate_matrix(self):
        """Generate a matrix-style .xlsx file and return (filename, bytes).

        Uses xlsxwriter for the same reason as _generate_excel — clean OOXML
        output without the repair-dialog issues that openpyxl introduced.
        """
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(_('xlsxwriter is required for Matrix export. Please install it.'))

        if not self.matrix_row_field_id or not self.matrix_col_field_id or not self.matrix_cell_field_id:
            raise UserError(_('Row axis, column axis, and cell value fields must be configured for matrix reports.'))

        records = self._get_records()
        row_field = self.matrix_row_field_id.name
        col_field = self.matrix_col_field_id.name
        cell_field = self.matrix_cell_field_id.name

        # Build unique row/col values and populate the cell data lookup
        row_values = []
        col_values = []
        seen_rows = set()
        seen_cols = set()
        cell_data = {}

        for record in records:
            rv = self._get_field_value(record, row_field) or '(empty)'
            cv = self._get_field_value(record, col_field) or '(empty)'
            cellv = self._get_field_value(record, cell_field)
            if rv not in seen_rows:
                seen_rows.add(rv)
                row_values.append(rv)
            if cv not in seen_cols:
                seen_cols.add(cv)
                col_values.append(cv)
            cell_data[(rv, cv)] = cellv

        row_values.sort()
        col_values.sort()

        row_label = self.matrix_row_label or self.matrix_row_field_id.field_description
        col_label = self.matrix_col_label or self.matrix_col_field_id.field_description

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        ws = wb.add_worksheet(self.name[:31])

        # ── Formats ─────────────────────────────────────────────────────────
        title_fmt = wb.add_format({
            'bold': True, 'font_size': 14,
            'font_color': '#FFFFFF', 'bg_color': '#2C5F8A',
            'align': 'left', 'valign': 'vcenter',
        })
        meta_fmt = wb.add_format({
            'italic': True, 'font_size': 10, 'font_color': '#555555',
            'align': 'left', 'valign': 'vcenter',
        })
        corner_fmt = wb.add_format({
            'bold': True, 'font_size': 11,
            'font_color': '#FFFFFF', 'bg_color': '#1F4E79',
            'align': 'center', 'valign': 'vcenter',
            'text_wrap': True, 'border': 1,
        })
        col_header_fmt = wb.add_format({
            'bold': True, 'font_size': 10,
            'font_color': '#FFFFFF', 'bg_color': '#2E75B6',
            'align': 'center', 'valign': 'vcenter',
            'text_wrap': True, 'border': 1,
        })
        row_label_fmt = wb.add_format({
            'bold': True, 'font_size': 10, 'bg_color': '#D6E4F0',
            'align': 'left', 'valign': 'vcenter', 'border': 1,
        })
        data_fmt = wb.add_format({
            'font_size': 10, 'align': 'center', 'valign': 'vcenter', 'border': 1,
        })
        data_alt_fmt = wb.add_format({
            'font_size': 10, 'align': 'center', 'valign': 'vcenter', 'border': 1,
            'bg_color': '#EBF2FA',
        })

        num_cols = len(col_values) + 1  # +1 for the row-label column
        r = 0  # 0-based row index

        def _write_merged(row_idx, text, fmt, height):
            """Write a full-width row, merging across all columns when there are 2+."""
            if num_cols > 1:
                ws.merge_range(row_idx, 0, row_idx, num_cols - 1, text, fmt)
            else:
                ws.write(row_idx, 0, text, fmt)
            ws.set_row(row_idx, height)

        # ── Title ────────────────────────────────────────────────────────────
        _write_merged(r, self.name, title_fmt, 28)
        r += 1

        # ── Meta rows ────────────────────────────────────────────────────────
        _write_merged(r, 'Model: %s' % self.model_id.name, meta_fmt, 15)
        r += 1
        domain_text = self.domain_description or ('Filter: %s' % (self.domain or 'None'))
        _write_merged(r, domain_text, meta_fmt, 15)
        r += 1
        _write_merged(
            r,
            'Records: %d  |  Rows: %d  |  Columns: %d' % (
                len(records), len(row_values), len(col_values)),
            meta_fmt, 15,
        )
        r += 1

        # ── Blank separator row ──────────────────────────────────────────────
        ws.set_row(r, 6)
        r += 1

        # ── Column-header row (row index 5) ──────────────────────────────────
        ws.write(r, 0, '%s \\ %s' % (row_label, col_label), corner_fmt)
        for ci, cv in enumerate(col_values, 1):
            ws.write(r, ci, cv, col_header_fmt)
        ws.set_row(r, 30)
        r += 1

        # ── Data rows ────────────────────────────────────────────────────────
        for ri, rv in enumerate(row_values):
            ws.write(r, 0, rv, row_label_fmt)
            for ci, cv in enumerate(col_values, 1):
                val = cell_data.get((rv, cv), '')
                fmt = data_alt_fmt if ri % 2 == 1 else data_fmt
                ws.write(r, ci, val or '', fmt)
            ws.set_row(r, 18)
            r += 1

        # ── Column widths ────────────────────────────────────────────────────
        ws.set_column(0, 0, 30)          # row-label column
        ws.set_column(1, num_cols, 18)   # data columns

        # ── Freeze: lock meta rows + blank + header row, and row-label column ─
        ws.freeze_panes(6, 1)

        wb.close()
        buf.seek(0)
        filename = '%s_matrix.xlsx' % self.name.replace('/', '-')
        return filename, buf.read()

    # ------------------------------------------------------------------
    # PDF generation
    # ------------------------------------------------------------------
    def _generate_pdf(self):
        """Generate a PDF using reportlab and return (filename, bytes)."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import (
                A0, A1, A2, A3, A4, landscape, portrait
            )
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.platypus import (
                SimpleDocTemplate, Table, TableStyle, Paragraph,
                Spacer, HRFlowable
            )
            from reportlab.lib.enums import TA_LEFT, TA_CENTER
        except ImportError:
            raise UserError(_('reportlab is required for PDF export. Please install it.'))

        PAGE_MAP = {'A4': A4, 'A3': A3, 'A2': A2, 'A1': A1, 'A0': A0}
        base_size = PAGE_MAP.get(self.pdf_page_size, A4)
        if self.pdf_orientation == 'landscape':
            page_size = landscape(base_size)
        else:
            page_size = portrait(base_size)

        records = self._get_records()
        headers = self._get_column_headers()
        rows = self._get_row_data(records)

        buf = io.BytesIO()
        margin = 15 * mm
        doc = SimpleDocTemplate(
            buf,
            pagesize=page_size,
            leftMargin=margin, rightMargin=margin,
            topMargin=margin, bottomMargin=margin,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'RBTitle', parent=styles['Heading1'],
            fontSize=16, textColor=colors.HexColor('#1F4E79'),
            spaceAfter=4,
        )
        meta_style = ParagraphStyle(
            'RBMeta', parent=styles['Normal'],
            fontSize=8, textColor=colors.HexColor('#555555'),
            spaceAfter=2,
        )

        story = []

        # Title
        story.append(Paragraph(self.name, title_style))
        story.append(Paragraph('Model: %s' % self.model_id.name, meta_style))
        domain_text = self.domain_description or ('Filter: %s' % (self.domain or 'None'))
        story.append(Paragraph(domain_text, meta_style))
        story.append(Paragraph('Records: %d' % len(records), meta_style))
        story.append(HRFlowable(width='100%', thickness=1,
                                 color=colors.HexColor('#2C5F8A'), spaceAfter=6))

        # Table
        usable_width = page_size[0] - 2 * margin
        num_cols = len(headers) or 1
        col_width = usable_width / num_cols

        header_row = [Paragraph('<b>%s</b>' % h, ParagraphStyle(
            'TH', parent=styles['Normal'], fontSize=8,
            textColor=colors.white, alignment=TA_CENTER
        )) for h in headers]

        table_data = [header_row]
        for row in rows:
            table_data.append([
                Paragraph(str(v) if v else '', ParagraphStyle(
                    'TD', parent=styles['Normal'], fontSize=7,
                    textColor=colors.black, alignment=TA_LEFT
                )) for v in row
            ])

        col_widths = [col_width] * num_cols
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)

        tbl_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E79')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.white, colors.HexColor('#EBF2FA')]),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#CCCCCC')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ])
        tbl.setStyle(tbl_style)
        story.append(tbl)

        doc.build(story)
        buf.seek(0)
        filename = '%s.pdf' % self.name.replace('/', '-')
        return filename, buf.read()

    def generate_report_bytes(self):
        """Public method to generate report — returns (filename, bytes, mimetype)."""
        self.ensure_one()
        fmt = self.report_format
        if fmt == 'excel':
            fname, data = self._generate_excel()
            mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif fmt == 'csv':
            fname, data = self._generate_csv()
            mime = 'text/csv'
        elif fmt == 'matrix':
            fname, data = self._generate_matrix()
            mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif fmt == 'pdf':
            fname, data = self._generate_pdf()
            mime = 'application/pdf'
        else:
            raise UserError(_('Unknown report format: %s') % fmt)
        return fname, data, mime

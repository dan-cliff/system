from odoo import api, fields, models, _
from odoo.exceptions import UserError


class InjuryRtwCase(models.Model):
    _name = 'injury.rtw.case'
    _description = 'Return to Work Case'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'
    _rec_name = 'name'

    name = fields.Char(
        'Case Reference', required=True, copy=False,
        readonly=True, default='New', tracking=True)

    incident_id = fields.Many2one(
        'incident.report', string='Linked Incident Report',
        tracking=True, index=True,
        help='Link this RTW case to the originating incident report.')

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True,
        tracking=True, index=True)
    job_title = fields.Char(related='employee_id.job_title', string='Job Title', readonly=True)
    department_id = fields.Many2one(related='employee_id.department_id', string='Department', readonly=True)

    case_manager_id = fields.Many2one(
        'res.users', string='Case Manager', tracking=True,
        domain=[('share', '=', False)])

    state = fields.Selection([
        ('draft',    'Draft'),
        ('active',   'Active'),
        ('on_hold',  'On Hold'),
        ('closed',   'Closed'),
    ], string='Status', default='draft', required=True,
       tracking=True, index=True)

    # Injury Details
    injury_date = fields.Date('Date of Injury / Illness', required=True, tracking=True)
    injury_type = fields.Selection([
        ('workplace',     'Workplace Injury'),
        ('non_workplace', 'Non-Workplace Injury'),
        ('illness',       'Occupational Illness'),
        ('disease',       'Occupational Disease'),
    ], string='Injury / Illness Type', tracking=True)
    body_part_affected = fields.Char('Body Part / Area Affected')
    injury_description = fields.Text('Injury / Illness Description')

    # Pre-injury Work Details
    pre_injury_hours = fields.Float('Pre-injury Hours per Week')
    pre_injury_duties = fields.Text('Pre-injury Duties / Role Description')

    # Insurance / Claim
    insurer_id = fields.Many2one(
        'res.partner', string='Insurer / WorkCover Authority', tracking=True,
        help='Select the insurer or WorkCover authority handling this claim.')
    primary_doctor_id = fields.Many2one(
        'res.partner', string='Primary Medical Practitioner', tracking=True,
        help='Select the primary treating doctor or medical practitioner.')
    claim_number = fields.Char('Claim Number')
    claim_accepted = fields.Boolean('Claim Accepted')
    claim_accepted_date = fields.Date('Claim Accepted Date')

    # Case Dates
    open_date = fields.Date('Case Opened', default=fields.Date.today)
    close_date = fields.Date('Case Closed', tracking=True)
    expected_rtw_date = fields.Date('Expected Return-to-Work Date', tracking=True)
    actual_rtw_date = fields.Date('Actual Return-to-Work Date', tracking=True)

    # Duration tracking
    days_open = fields.Integer(
        'Days Open', compute='_compute_days_open', store=False)
    days_open_label = fields.Char(
        'Duration Open', compute='_compute_days_open', store=False,
        help='Human-readable duration the case has been open.')

    # Additional
    notes = fields.Text('General Notes')

    # Sub-record One2manys
    case_note_ids = fields.One2many('injury.case.note', 'case_id', string='Case Notes')
    appointment_ids = fields.One2many('injury.medical.appointment', 'case_id', string='Medical Appointments')
    meeting_ids = fields.One2many('injury.meeting', 'case_id', string='Meetings & Communications')
    file_note_ids = fields.One2many('injury.file.note', 'case_id', string='File Notes')
    cost_ids = fields.One2many('injury.cost', 'case_id', string='Costs')
    rtw_plan_ids = fields.One2many('injury.rtw.plan', 'case_id', string='RTW Plans')
    certificate_ids = fields.One2many('injury.medical.certificate', 'case_id', string='Medical Certificates')

    # Document count (aggregated across all sub-registers)
    document_count = fields.Integer(
        compute='_compute_document_count', string='Documents')

    # Computed Counts
    case_note_count = fields.Integer(compute='_compute_counts')
    appointment_count = fields.Integer(compute='_compute_counts')
    meeting_count = fields.Integer(compute='_compute_counts')
    file_note_count = fields.Integer(compute='_compute_counts')
    cost_count = fields.Integer(compute='_compute_counts')
    rtw_plan_count = fields.Integer(compute='_compute_counts')
    certificate_count = fields.Integer(compute='_compute_counts')
    total_cost = fields.Monetary(
        'Total Costs', compute='_compute_total_cost',
        currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)

    @api.depends('open_date', 'close_date', 'state')
    def _compute_days_open(self):
        today = fields.Date.today()
        for rec in self:
            start = rec.open_date
            if not start:
                rec.days_open = 0
                rec.days_open_label = ''
                continue
            end = (rec.close_date
                   if rec.state == 'closed' and rec.close_date
                   else today)
            d = max((end - start).days, 0)
            rec.days_open = d
            if d < 7:
                rec.days_open_label = f"{d} day{'s' if d != 1 else ''}"
            elif d < 30:
                weeks = d // 7
                rec.days_open_label = f"{weeks} week{'s' if weeks != 1 else ''}"
            elif d < 365:
                months = max(round(d / 30.44), 1)
                rec.days_open_label = f"{months} month{'s' if months != 1 else ''}"
            else:
                years = d // 365
                rem_months = round((d % 365) / 30.44)
                if rem_months >= 12:
                    years += 1
                    rem_months = 0
                if rem_months > 0:
                    rec.days_open_label = (
                        f"{years} year{'s' if years != 1 else ''}, "
                        f"{rem_months} month{'s' if rem_months != 1 else ''}"
                    )
                else:
                    rec.days_open_label = f"{years} year{'s' if years != 1 else ''}"

    def _compute_document_count(self):
        for rec in self:
            rec.document_count = self.env['injury.case.document'].search_count(
                [('case_id', '=', rec.id)])

    @api.depends(
        'case_note_ids', 'appointment_ids', 'meeting_ids',
        'file_note_ids', 'cost_ids', 'rtw_plan_ids', 'certificate_ids')
    def _compute_counts(self):
        for rec in self:
            rec.case_note_count    = len(rec.case_note_ids)
            rec.appointment_count  = len(rec.appointment_ids)
            rec.meeting_count      = len(rec.meeting_ids)
            rec.file_note_count    = len(rec.file_note_ids)
            rec.cost_count         = len(rec.cost_ids)
            rec.rtw_plan_count     = len(rec.rtw_plan_ids)
            rec.certificate_count  = len(rec.certificate_ids)

    @api.depends('cost_ids.amount')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = sum(rec.cost_ids.mapped('amount'))

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id and self.employee_id.resource_calendar_id:
            self.pre_injury_hours = self.employee_id.resource_calendar_id.hours_per_week

    @api.onchange('incident_id')
    def _onchange_incident_id(self):
        inc = self.incident_id
        if not inc:
            return

        # Employee
        if inc.employee_id:
            self.employee_id = inc.employee_id

        # Date of injury — incident stores a Datetime; we just need the date
        if inc.date_occurred:
            self.injury_date = inc.date_occurred.date()

        # Injury / illness type — derive from incident category booleans
        if inc.is_injury:
            self.injury_type = 'workplace'
        elif inc.is_illness:
            self.injury_type = 'illness'

        # Body part
        if inc.injury_body_parts_display:
            self.body_part_affected = inc.injury_body_parts_display

        # Description
        if inc.description:
            self.injury_description = inc.description

        # Case manager — use the incident's responsible manager if set
        if inc.responsible_manager_id:
            self.case_manager_id = inc.responsible_manager_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('injury.rtw.case') or 'New'
        return super().create(vals_list)

    def action_activate(self):
        for rec in self:
            rec.state = 'active'
            rec.message_post(body=_('Case activated.'), subtype_xmlid='mail.mt_note')

    def action_hold(self):
        for rec in self:
            rec.state = 'on_hold'
            rec.message_post(body=_('Case placed on hold.'), subtype_xmlid='mail.mt_note')

    def action_close(self):
        for rec in self:
            rec.state = 'closed'
            rec.close_date = fields.Date.today()
            rec.message_post(body=_('Case closed.'), subtype_xmlid='mail.mt_note')

    def action_reopen(self):
        for rec in self:
            rec.state = 'active'
            rec.close_date = False
            rec.message_post(body=_('Case reopened.'), subtype_xmlid='mail.mt_note')

    # Smart button actions
    def action_view_case_notes(self):
        return self._action_view_related('injury.case.note', 'case_id', 'Case Notes')

    def action_view_appointments(self):
        return self._action_view_related('injury.medical.appointment', 'case_id', 'Medical Appointments')

    def action_view_meetings(self):
        return self._action_view_related('injury.meeting', 'case_id', 'Meetings & Communications')

    def action_view_file_notes(self):
        return self._action_view_related('injury.file.note', 'case_id', 'File Notes')

    def action_view_costs(self):
        return self._action_view_related('injury.cost', 'case_id', 'Costs')

    def action_view_rtw_plans(self):
        return self._action_view_related('injury.rtw.plan', 'case_id', 'RTW Plans')

    def action_view_certificates(self):
        return self._action_view_related('injury.medical.certificate', 'case_id', 'Medical Certificates')

    def action_open_report_wizard(self):
        """Open the PDF export wizard for this case."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Export RTW Case PDF',
            'res_model': 'injury.case.report.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_case_id': self.id},
        }

    def action_view_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Case Documents',
            'res_model': 'injury.case.document',
            'view_mode': 'list',
            'domain': [('case_id', '=', self.id)],
            'context': {'default_case_id': self.id},
        }

    def _action_view_related(self, model, field, title):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': model,
            'view_mode': 'list,form',
            'domain': [(field, '=', self.id)],
            'context': {field: self.id, 'default_' + field: self.id},
        }

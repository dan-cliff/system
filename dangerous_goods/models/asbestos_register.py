# -*- coding: utf-8 -*-
from odoo import api, fields, models
from datetime import date


class AsbestosRegister(models.Model):
    _name = 'dg.asbestos'
    _description = 'Asbestos Register'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'
    _rec_name = 'item_description'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        'Reference', readonly=True, default='New', copy=False, tracking=True)
    item_description = fields.Char(
        'Item Description', required=True, tracking=True,
        help='Brief description of the asbestos-containing material (ACM) item')
    active = fields.Boolean(default=True, tracking=True)

    # ── Location ──────────────────────────────────────────────────────────────
    building_id = fields.Many2one(
        'dg.building', string='Building / Site',
        required=True, tracking=True)
    floor_level = fields.Char('Floor / Level',
                              help='e.g. Ground Floor, Level 2, Roof')
    area_description = fields.Char(
        'Area / Room', required=True,
        help='e.g. Plant room, Amenities block, External wall - North face')
    specific_location = fields.Text(
        'Specific Location Details',
        help='Precise description to allow the ACM to be located')
    gps_coordinates = fields.Char('GPS Coordinates')

    # ── ACM Classification ────────────────────────────────────────────────────
    asbestos_type = fields.Selection([
        ('friable', 'Friable'),
        ('non_friable', 'Non-Friable (Bonded)'),
        ('unknown', 'Unknown / To Be Confirmed'),
    ], string='Asbestos Type', required=True, tracking=True,
        help='Friable = can be crumbled to fine powder by hand pressure. '
             'Non-friable (bonded) = asbestos fibres are firmly bound in a solid matrix.')
    asbestos_form_id = fields.Many2one(
        'dg.asbestos.form', string='Form / Material Type',
        help='e.g. Fibro sheeting, pipe lagging, spray coating, floor tiles')
    fibre_type = fields.Selection([
        ('chrysotile', 'Chrysotile (White Asbestos)'),
        ('amosite', 'Amosite (Brown Asbestos)'),
        ('crocidolite', 'Crocidolite (Blue Asbestos)'),
        ('mixed', 'Mixed Fibre Types'),
        ('unknown', 'Unknown'),
    ], string='Fibre Type')
    confirmed_by_sampling = fields.Boolean(
        'Confirmed by Sampling / Analysis',
        help='Tick if fibre type has been confirmed by laboratory analysis')
    sample_date = fields.Date('Sample / Analysis Date')
    laboratory = fields.Char('Laboratory')
    quantity = fields.Float('Estimated Quantity')
    quantity_uom = fields.Selection([
        ('m2', 'm²'), ('m', 'm (linear)'), ('m3', 'm³'),
        ('units', 'items / units'), ('kg', 'kg'),
    ], string='Unit', default='m2')

    # ── Condition & Risk ──────────────────────────────────────────────────────
    condition = fields.Selection([
        ('good', 'Good — Intact, No Visible Damage'),
        ('fair', 'Fair — Minor Surface Damage / Wear'),
        ('poor', 'Poor — Significant Damage / Deterioration'),
        ('very_poor', 'Very Poor — Badly Damaged / Friable'),
    ], string='Condition', required=True, tracking=True)
    accessibility = fields.Selection([
        ('inaccessible', 'Inaccessible to Occupants'),
        ('limited', 'Limited Access Only'),
        ('accessible', 'Accessible to Occupants'),
    ], string='Accessibility')
    risk_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('extreme', 'Extreme'),
    ], string='Risk Level', required=True, tracking=True)
    risk_assessment_notes = fields.Text('Risk Assessment Notes')

    # ── Control Measures ──────────────────────────────────────────────────────
    control_measure_ids = fields.Many2many(
        'dg.control.measure', 'dg_asbestos_control_rel',
        'asbestos_id', 'measure_id', string='Control Measures')
    control_measure_notes = fields.Text('Control Measure Details')
    signage_present = fields.Boolean(
        'Warning Signage in Place',
        help='Asbestos warning signs displayed as required by WHS Reg 438')
    encapsulated = fields.Boolean(
        'Encapsulated / Sealed',
        help='ACM has been encapsulated with a sealant to prevent fibre release')
    encapsulation_date = fields.Date('Encapsulation Date')
    encapsulation_notes = fields.Text('Encapsulation Details')

    # ── Inspection History ────────────────────────────────────────────────────
    identified_date = fields.Date(
        'Date First Identified', required=True,
        help='Date the ACM was first identified at this workplace')
    identified_by = fields.Char('Identified By')
    last_inspection_date = fields.Date('Last Inspection Date', tracking=True)
    next_inspection_date = fields.Date('Next Inspection Date', tracking=True)
    inspection_frequency = fields.Selection([
        ('3months', 'Every 3 Months'),
        ('6months', 'Every 6 Months'),
        ('12months', 'Annually'),
        ('24months', 'Every 2 Years'),
        ('other', 'Other — See Notes'),
    ], string='Inspection Frequency', default='12months')
    inspection_ids = fields.One2many(
        'dg.asbestos.inspection', 'asbestos_id', string='Inspection Records')
    inspection_count = fields.Integer(
        'Inspections', compute='_compute_inspection_count')
    inspection_overdue = fields.Boolean(
        'Inspection Overdue', compute='_compute_overdue', store=True)

    # ── Removal ───────────────────────────────────────────────────────────────
    removal_required = fields.Boolean('Removal Required', tracking=True)
    removal_priority = fields.Selection([
        ('immediate', 'Immediate'),
        ('urgent', 'Urgent (within 3 months)'),
        ('planned', 'Planned (3–12 months)'),
        ('long_term', 'Long-term (> 12 months)'),
    ], string='Removal Priority')
    removal_date_planned = fields.Date('Planned Removal Date')
    removal_date_actual = fields.Date('Actual Removal Date', tracking=True)
    removal_remover_id = fields.Many2one(
        'dg.asbestos.remover', string='Licensed Removalist')
    removal_licence_class = fields.Char(
        'Removalist Licence Class',
        compute='_compute_remover_licence', store=True)
    removal_waste_disposal = fields.Text(
        'Waste Disposal Details',
        help='Disposal facility, transport details, waste tracking number')
    removal_clearance_cert = fields.Boolean(
        'Clearance Certificate Obtained',
        help='Independent hygienist clearance certificate obtained post-removal')
    removal_clearance_date = fields.Date('Clearance Certificate Date')
    removal_notes = fields.Text('Removal Notes')

    # ── Status ────────────────────────────────────────────────────────────────
    acm_status = fields.Selection([
        ('in_situ', 'In Situ — Being Managed'),
        ('removed', 'Removed'),
        ('partially_removed', 'Partially Removed'),
        ('not_confirmed', 'Presence Not Confirmed'),
    ], string='ACM Status', default='in_situ', required=True, tracking=True)

    # ── WHS Compliance (Part 8.3) ─────────────────────────────────────────────
    register_accessible = fields.Boolean(
        'Register Accessible to Workers', default=True,
        help='WHS Reg 425 — The asbestos register must be accessible to workers '
             'at the workplace at all times when work is being carried out.')
    whs_reg_reference = fields.Char(
        'WHS Regulation Reference',
        default='WHS Regulations 2017, Part 8.3 — Asbestos')

    # ── Administration ────────────────────────────────────────────────────────
    responsible_person_id = fields.Many2one(
        'res.users', string='Responsible Person', tracking=True)
    notes = fields.Text('Additional Notes')
    attachment_count = fields.Integer(
        'Attachments', compute='_compute_attachment_count')

    # ── Compute ───────────────────────────────────────────────────────────────
    def _compute_inspection_count(self):
        for rec in self:
            rec.inspection_count = len(rec.inspection_ids)

    @api.depends('next_inspection_date')
    def _compute_overdue(self):
        today = date.today()
        for rec in self:
            rec.inspection_overdue = bool(
                rec.next_inspection_date and rec.next_inspection_date < today)

    @api.depends('removal_remover_id.licence_class')
    def _compute_remover_licence(self):
        for rec in self:
            if rec.removal_remover_id and rec.removal_remover_id.licence_class:
                selection = dict(
                    self.env['dg.asbestos.remover']._fields[
                        'licence_class'].selection)
                rec.removal_licence_class = selection.get(
                    rec.removal_remover_id.licence_class, '')
            else:
                rec.removal_licence_class = ''

    def _compute_attachment_count(self):
        Attachment = self.env['ir.attachment']
        for rec in self:
            rec.attachment_count = Attachment.search_count([
                ('res_model', '=', self._name),
                ('res_id', '=', rec.id),
            ])

    # ── Sequence ──────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'dg.asbestos') or 'New'
        return super().create(vals_list)

    # ── Status Actions ────────────────────────────────────────────────────────
    def action_mark_removed(self):
        self.acm_status = 'removed'

    def action_mark_in_situ(self):
        self.acm_status = 'in_situ'

    def action_view_inspections(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Inspection Records',
            'res_model': 'dg.asbestos.inspection',
            'view_mode': 'list,form',
            'domain': [('asbestos_id', '=', self.id)],
            'context': {'default_asbestos_id': self.id},
        }

    def action_print_register(self):
        return self.env.ref(
            'dangerous_goods.action_report_asbestos_register'
        ).report_action(self)


class DgAsbestosInspection(models.Model):
    _name = 'dg.asbestos.inspection'
    _description = 'Asbestos Inspection Record'
    _order = 'inspection_date desc'

    asbestos_id = fields.Many2one(
        'dg.asbestos', string='Asbestos Item',
        required=True, ondelete='cascade', index=True)
    inspection_date = fields.Date('Inspection Date', required=True)
    inspected_by = fields.Char('Inspected By', required=True)
    condition_found = fields.Selection([
        ('good', 'Good — Intact'),
        ('fair', 'Fair — Minor Damage'),
        ('poor', 'Poor — Significant Damage'),
        ('very_poor', 'Very Poor — Badly Damaged'),
    ], string='Condition Found', required=True)
    findings = fields.Text('Findings / Observations')
    action_required = fields.Boolean('Action Required')
    action_details = fields.Text('Action Details')
    next_inspection = fields.Date('Next Inspection Due')
    photo_ids = fields.Many2many(
        'ir.attachment', 'dg_asbestos_inspection_photo_rel',
        'inspection_id', 'attachment_id', string='Photos / Documents')

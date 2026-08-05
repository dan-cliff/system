# -*- coding: utf-8 -*-
from odoo import api, fields, models
from datetime import date, timedelta


class ChemicalRegister(models.Model):
    _name = 'dg.chemical'
    _description = 'Chemical Register'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'product_name, id'
    _rec_name = 'product_name'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        'Reference', readonly=True, default='New', copy=False, tracking=True)
    product_name = fields.Char('Product Name', required=True, tracking=True)
    chemical_name = fields.Char('Chemical / Substance Name', tracking=True)
    trade_name = fields.Char('Trade Name / Brand')
    cas_number = fields.Char(
        'CAS Number',
        help='Chemical Abstracts Service Registry Number, e.g. 67-64-1')
    un_number = fields.Char(
        'UN Number',
        help='4-digit United Nations dangerous goods transport number, e.g. UN1090')
    active = fields.Boolean(default=True, tracking=True)

    # ── Status (pipeline stage) ───────────────────────────────────────────────
    stage_id = fields.Many2one(
        'dg.chemical.stage', string='Status',
        default=lambda self: self.env.ref(
            'dangerous_goods.stage_chemical_active', raise_if_not_found=False),
        tracking=True)
    # Stored code for domain filters / view conditions (e.g. state == 'active')
    state = fields.Char(related='stage_id.code', store=True, string='Stage Code')

    # ── Physical Properties ───────────────────────────────────────────────────
    physical_state = fields.Selection([
        ('solid', 'Solid'),
        ('liquid', 'Liquid'),
        ('gas', 'Gas'),
        ('paste', 'Paste / Gel'),
        ('powder', 'Powder / Dust'),
        ('other', 'Other'),
    ], string='Physical State')
    colour = fields.Char('Colour / Appearance')
    odour = fields.Char('Odour')
    flash_point = fields.Char('Flash Point', help='e.g. 23°C (closed cup)')
    boiling_point = fields.Char('Boiling Point')
    vapour_pressure = fields.Char('Vapour Pressure')
    specific_gravity = fields.Char('Specific Gravity / Density')
    solubility = fields.Char('Solubility in Water')
    ph = fields.Char('pH (if applicable)')

    # ── Supplier / SDS ────────────────────────────────────────────────────────
    supplier_id = fields.Many2one('res.partner', string='Supplier / Manufacturer',
                                  tracking=True)
    supplier_address = fields.Text('Supplier Address')
    supplier_emergency_contact = fields.Char(
        'Supplier Emergency Phone',
        help='24-hour emergency contact number on the SDS')
    sds_version = fields.Char('SDS Version')
    sds_issue_date = fields.Date('SDS Issue Date')
    sds_review_date = fields.Date('SDS Review Date / Expiry',
                                  tracking=True)
    sds_overdue = fields.Boolean(
        'SDS Review Overdue', compute='_compute_sds_overdue', store=True)
    sds_document_ids = fields.Many2many(
        'ir.attachment', 'dg_chemical_sds_rel',
        'chemical_id', 'attachment_id', string='SDS Documents')

    # ── Location & Quantities ──────────────────────────────────────────────────
    building_id = fields.Many2one('dg.building', string='Building / Site',
                                  tracking=True)
    storage_location_ids = fields.Many2many(
        'dg.storage.location', string='Storage Locations')
    quantity_on_hand = fields.Float('Quantity on Hand')
    max_quantity = fields.Float(
        'Maximum Quantity',
        help='Maximum quantity stored at the workplace at any one time')
    quantity_uom = fields.Selection([
        ('kg', 'kg'), ('g', 'g'), ('L', 'L'), ('mL', 'mL'),
        ('units', 'units'), ('m3', 'm³'), ('t', 't'),
    ], string='Unit', default='kg')
    container_type = fields.Char('Container / Packaging Type',
                                 help='e.g. 20L pail, 200L drum, gas cylinder')

    # ── Australian WHS Compliance ──────────────────────────────────────────────
    adg_class_id = fields.Many2one(
        'dg.adg.class', string='ADG Transport Class',
        help='Australian Dangerous Goods Code (ADG Code 7.8) transport classification')
    storage_class_id = fields.Many2one(
        'dg.storage.class', string='DG Storage Class (AS 3833)')
    packing_group = fields.Selection([
        ('i', 'I — Great Danger'),
        ('ii', 'II — Medium Danger'),
        ('iii', 'III — Minor Danger'),
    ], string='Packing Group')
    scheduled_substance = fields.Boolean(
        'Scheduled Substance',
        help='Substance listed under the Poisons Standard (SUSMP)')
    schedule_number = fields.Char(
        'Poisons Schedule',
        help='e.g. Schedule 5, Schedule 6, Schedule 7, Schedule 8')
    prohibited_substance = fields.Boolean(
        'Prohibited Substance',
        help='Use is prohibited under relevant WHS Regulations (e.g. WHS Reg Schedule 14)')
    prohibited_reason = fields.Text('Prohibition Details')
    manifest_quantity = fields.Boolean(
        'Exceeds Manifest Quantity',
        help='Quantity on site exceeds manifest threshold under WHS Reg Schedule 15')
    placard_quantity = fields.Boolean(
        'Exceeds Placard Quantity',
        help='Quantity on site exceeds placard threshold under WHS Reg Schedule 13')
    workplace_exposure_standard = fields.Char(
        'Workplace Exposure Standard (WES)',
        help='TWA/STEL per Safe Work Australia Workplace Exposure Standards for Airborne Contaminants')
    biological_limit = fields.Char(
        'Biological Exposure Index / Limit')

    # ── GHS Classification ────────────────────────────────────────────────────
    ghs_signal_word = fields.Selection([
        ('danger', 'DANGER'),
        ('warning', 'WARNING'),
        ('none', 'No Signal Word'),
    ], string='Signal Word', tracking=True)
    ghs_hazard_class_ids = fields.Many2many(
        'ghs.hazard.class', 'dg_chemical_hazard_class_rel',
        'chemical_id', 'class_id', string='GHS Hazard Classes')
    ghs_pictogram_ids = fields.Many2many(
        'ghs.pictogram', 'dg_chemical_pictogram_rel',
        'chemical_id', 'pictogram_id', string='GHS Pictograms')
    ghs_hazard_statement_ids = fields.Many2many(
        'ghs.hazard.statement', 'dg_chemical_h_statement_rel',
        'chemical_id', 'statement_id', string='Hazard Statements (H-codes)')
    ghs_precautionary_statement_ids = fields.Many2many(
        'ghs.precautionary.statement', 'dg_chemical_p_statement_rel',
        'chemical_id', 'statement_id', string='Precautionary Statements (P-codes)')

    # ── Health Hazard Data ─────────────────────────────────────────────────────
    carcinogen = fields.Boolean('Known / Suspected Carcinogen (GHS CMR)')
    carcinogen_classification = fields.Char(
        'Carcinogen Classification',
        help='e.g. Category 1A, Category 1B, Category 2')
    mutagen = fields.Boolean('Germ Cell Mutagen')
    reproductive_toxicant = fields.Boolean('Reproductive Toxicant')

    # ── Safety Controls ───────────────────────────────────────────────────────
    ppe_ids = fields.Many2many(
        'dg.ppe.type', 'dg_chemical_ppe_rel',
        'chemical_id', 'ppe_id', string='Required PPE')
    engineering_controls = fields.Text(
        'Engineering Controls',
        help='e.g. fume cupboard, local exhaust ventilation (LEV), bunded storage')
    administrative_controls = fields.Text(
        'Administrative Controls',
        help='e.g. restricted access, training requirements, permit-to-work')
    first_aid_measures = fields.Text(
        'First Aid Measures',
        help='General first aid. Include eye contact, skin contact, inhalation, ingestion.')
    fire_fighting_measures = fields.Text('Fire Fighting Measures')
    spill_procedures = fields.Text('Spill / Accidental Release Procedures')
    emergency_procedures = fields.Text('Emergency Procedures')
    disposal_methods = fields.Text('Disposal Methods / Waste Disposal')
    incompatible_materials = fields.Text(
        'Incompatible Materials',
        help='Substances to keep separate from this chemical')
    storage_requirements = fields.Text('Special Storage Requirements')

    # ── Administration ────────────────────────────────────────────────────────
    responsible_person_id = fields.Many2one(
        'res.users', string='Responsible Person', tracking=True)
    chemical_owner_id = fields.Many2one(
        'hr.employee', string='Chemical Owner', tracking=True,
        help='Employee responsible for this chemical. They will be notified 30 days before expiry.')
    issued_date = fields.Date('Issue Date',
                              help='Date the chemical was received or issued into the workplace.')
    expiry_date = fields.Date('Expiry Date', tracking=True,
                              help='Physical expiry / use-by date of the substance.')
    expiry_overdue = fields.Boolean(
        'Expired', compute='_compute_expiry_overdue', store=True)
    last_review_date = fields.Date('Last Review Date')
    next_review_date = fields.Date('Next Review Date', tracking=True)
    notes = fields.Text('Additional Notes')
    attachment_count = fields.Integer(
        'SDS Attachments', compute='_compute_attachment_count')

    # ── Compute ───────────────────────────────────────────────────────────────
    @api.depends('sds_review_date')
    def _compute_sds_overdue(self):
        today = date.today()
        for rec in self:
            rec.sds_overdue = bool(rec.sds_review_date and rec.sds_review_date < today)

    @api.depends('expiry_date')
    def _compute_expiry_overdue(self):
        today = date.today()
        for rec in self:
            rec.expiry_overdue = bool(rec.expiry_date and rec.expiry_date < today)

    def _compute_attachment_count(self):
        for rec in self:
            rec.attachment_count = len(rec.sds_document_ids)

    # ── Cron: 30-day expiry notifications ────────────────────────────────────
    @api.model
    def _cron_notify_expiry_upcoming(self):
        """Run daily. Creates a chatter activity on any chemical expiring in
        exactly 30 days and assigns it to the Chemical Owner (or Responsible
        Person as fallback). Skips records that already have a pending
        'Chemical Expiry' activity to avoid duplicates."""
        notify_date = date.today() + timedelta(days=30)

        chemicals = self.search([
            ('expiry_date', '=', notify_date),
            ('active', '=', True),
            ('stage_id.fold', '=', False),
        ])
        if not chemicals:
            return

        activity_type = self.env.ref(
            'mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            activity_type = self.env['mail.activity.type'].search(
                [('name', 'ilike', 'to-do')], limit=1)
        if not activity_type:
            return

        for chemical in chemicals:
            # Resolve the user to notify
            user = self.env.user  # safe fallback
            if chemical.chemical_owner_id and chemical.chemical_owner_id.user_id:
                user = chemical.chemical_owner_id.user_id
            elif chemical.responsible_person_id:
                user = chemical.responsible_person_id

            # Skip if a 30-day expiry activity already exists for this record
            already_exists = self.env['mail.activity'].search_count([
                ('res_model', '=', self._name),
                ('res_id', '=', chemical.id),
                ('activity_type_id', '=', activity_type.id),
                ('summary', '=', 'Chemical Expiry — 30 Day Notice'),
            ])
            if already_exists:
                continue

            expiry_str = chemical.expiry_date.strftime('%d/%m/%Y')
            owner_name = (
                chemical.chemical_owner_id.name
                if chemical.chemical_owner_id
                else user.name
            )
            chemical.activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=chemical.expiry_date,
                summary='Chemical Expiry — 30 Day Notice',
                note=(
                    f'<p><strong>{chemical.product_name}</strong> '
                    f'({chemical.name}) expires on '
                    f'<strong>{expiry_str}</strong>.</p>'
                    f'<p>Please review the stock and arrange disposal or '
                    f'replacement before the expiry date. '
                    f'Chemical Owner: <strong>{owner_name}</strong>.</p>'
                ),
                user_id=user.id,
            )

    # ── Sequence ──────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'dg.chemical') or 'New'
        return super().create(vals_list)

    # ── Actions ───────────────────────────────────────────────────────────────
    def action_set_active(self):
        self.stage_id = self.env.ref('dangerous_goods.stage_chemical_active')

    def action_set_review(self):
        self.stage_id = self.env.ref('dangerous_goods.stage_chemical_review')

    def action_set_discontinued(self):
        self.stage_id = self.env.ref('dangerous_goods.stage_chemical_discontinued')

    def action_print_register(self):
        return self.env.ref(
            'dangerous_goods.action_report_chemical_register'
        ).report_action(self)

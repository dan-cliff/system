from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class EmployeeHealthcare(models.Model):
    _name = 'employee.healthcare'
    _description = 'Employee Healthcare Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'employee_id'
    _order = 'employee_id'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
        index=True,
    )
    # Stored so the record appears in searches / _rec_name display
    name = fields.Char(
        related='employee_id.name',
        store=True,
        string='Employee Name',
    )
    department_id = fields.Many2one(
        related='employee_id.department_id',
        string='Department',
        store=True,
    )
    job_id = fields.Many2one(
        related='employee_id.job_id',
        string='Job Position',
        store=True,
    )

    # ── Medicare ──────────────────────────────────────────────────────────
    medicare_number = fields.Char(
        string='Medicare Number',
        tracking=True,
    )
    medicare_expiry = fields.Date(
        string='Medicare Card Expiry',
        tracking=True,
    )

    # ── Private Health Insurance ──────────────────────────────────────────
    private_health_insurer_id = fields.Many2one(
        'employee.healthcare.insurer',
        string='Private Health Insurer',
        tracking=True,
    )
    private_health_member_number = fields.Char(
        string='Membership Number',
        tracking=True,
    )
    private_health_level = fields.Char(
        string='Cover Level',
        help='e.g. Gold, Silver, Bronze, Basic',
        tracking=True,
    )

    # ── Ambulance Membership ──────────────────────────────────────────────
    ambulance_provider_id = fields.Many2one(
        'employee.healthcare.ambulance.provider',
        string='Ambulance Provider',
        tracking=True,
    )
    ambulance_membership_number = fields.Char(
        string='Ambulance Membership Number',
        tracking=True,
    )
    ambulance_membership_expiry = fields.Date(
        string='Ambulance Membership Expiry',
        tracking=True,
    )

    # ── Child one2many relationships ──────────────────────────────────────
    healthcare_alert_ids = fields.One2many(
        'employee.healthcare.alert', 'healthcare_id',
        string='Health Alerts',
    )
    healthcare_medication_ids = fields.One2many(
        'employee.healthcare.medication', 'healthcare_id',
        string='Medications',
    )
    healthcare_allergy_ids = fields.One2many(
        'employee.healthcare.allergy', 'healthcare_id',
        string='Allergies',
    )
    healthcare_directive_ids = fields.One2many(
        'employee.healthcare.directive', 'healthcare_id',
        string='Advanced Directives / Proxies',
    )

    # ── Indicators ────────────────────────────────────────────────────────
    healthcare_indicator_ids = fields.Many2many(
        'employee.healthcare.indicator',
        'employee_healthcare_record_indicator_rel',
        'healthcare_id', 'indicator_id',
        string='Healthcare Indicators',
    )

    # ── Medicare date range search helpers (for search view From / To) ──────
    medicare_expiry_from = fields.Date(
        string='Medicare Expiry From',
        store=False,
        compute='_compute_medicare_expiry_range',
        search='_search_medicare_expiry_from',
    )
    medicare_expiry_to = fields.Date(
        string='Medicare Expiry To',
        store=False,
        compute='_compute_medicare_expiry_range',
        search='_search_medicare_expiry_to',
    )

    def _compute_medicare_expiry_range(self):
        # These fields are search-only; compute always returns False.
        for rec in self:
            rec.medicare_expiry_from = False
            rec.medicare_expiry_to = False

    def _search_medicare_expiry_from(self, operator, value):
        # Search views always pass operator='=' for typed field values; we
        # intentionally ignore it and apply >= so the field acts as a range
        # lower-bound regardless of what the caller specifies.
        return [('medicare_expiry', '>=', value)]

    def _search_medicare_expiry_to(self, operator, value):
        # Same rationale as _search_medicare_expiry_from — always upper-bound.
        return [('medicare_expiry', '<=', value)]

    # ── Medicare status (for list view colour coding) ─────────────────────
    medicare_status = fields.Selection(
        selection=[
            ('expired', 'Expired'),
            ('next_month', 'Next Month'),
            ('valid', 'Valid'),
            ('none', 'None'),
        ],
        string='Medicare Status',
        compute='_compute_medicare_status',
        store=False,
    )

    @api.depends('medicare_expiry')
    def _compute_medicare_status(self):
        today = fields.Date.today()
        next_month_start = today.replace(day=1) + relativedelta(months=1)
        # Last day of next month: start of the month after that, minus one day.
        next_month_end = next_month_start + relativedelta(months=1, days=-1)
        for rec in self:
            if not rec.medicare_expiry:
                rec.medicare_status = 'none'
            elif rec.medicare_expiry < today:
                rec.medicare_status = 'expired'
            elif rec.medicare_expiry <= next_month_end:
                rec.medicare_status = 'next_month'
            else:
                rec.medicare_status = 'valid'

    # ── Verification ─────────────────────────────────────────────────────
    last_verified = fields.Datetime(
        string='Last Verified',
        readonly=True,
        tracking=True,
        help='Date and time the employee last confirmed this profile is accurate.',
    )
    days_since_last_verified = fields.Integer(
        string='Days Since Last Verified',
        compute='_compute_days_since_last_verified',
        search='_search_days_since_last_verified',
        store=False,
        help='Number of whole days since the employee last confirmed this profile. '
             'Returns -1 if the profile has never been verified.',
    )

    @api.depends('last_verified')
    def _compute_days_since_last_verified(self):
        today = fields.Date.today()
        for rec in self:
            if not rec.last_verified:
                rec.days_since_last_verified = -1
            else:
                delta = today - rec.last_verified.date()
                rec.days_since_last_verified = delta.days

    def _search_days_since_last_verified(self, operator, value):
        """Translate a days_since_last_verified domain leaf into a last_verified comparison.

        Never-verified records have days_since = -1 (treated as infinity):
          - >= / >  operators include never-verified records (OR last_verified IS NULL)
          - <= / <  operators exclude never-verified records
          - =       on -1 maps directly to last_verified IS NULL
        """
        today = fields.Date.today()

        n = int(value)

        # Special case: -1 means never verified (last_verified IS NULL).
        if n == -1:
            if operator in ('=', '<='):
                return [('last_verified', '=', False)]
            if operator in ('!=', '>'):
                return [('last_verified', '!=', False)]
            return []

        # The date on which last_verified.date() == today - n days.
        target = today - relativedelta(days=n)
        next_day = target + relativedelta(days=1)

        # Higher days_since  →  earlier last_verified, so operators invert.
        if operator == '=':
            # last_verified.date() == target
            return [('last_verified', '>=', str(target)),
                    ('last_verified', '<', str(next_day))]
        if operator == '!=':
            return ['|',
                    ('last_verified', '<', str(target)),
                    ('last_verified', '>=', str(next_day))]
        if operator == '>':
            # more days since  →  earlier date; also include never-verified
            return ['|',
                    ('last_verified', '=', False),
                    ('last_verified', '<', str(target))]
        if operator == '>=':
            return ['|',
                    ('last_verified', '=', False),
                    ('last_verified', '<', str(next_day))]
        if operator == '<':
            # fewer days since  →  more recent date; exclude never-verified
            return [('last_verified', '>=', str(next_day))]
        if operator == '<=':
            return [('last_verified', '>=', str(target))]
        return []

    _employee_uniq = models.Constraint(
        'unique(employee_id)',
        'Each employee can only have one healthcare record.',
    )

    # ── Indicator evaluation ──────────────────────────────────────────────
    def write(self, vals):
        result = super().write(vals)
        # Re-evaluate indicators after every save, but skip when the write
        # itself is the indicator update (prevents infinite recursion).
        if 'healthcare_indicator_ids' not in vals:
            self.action_evaluate_healthcare_indicators()
        return result

    def action_evaluate_healthcare_indicators(self):
        """Re-evaluate all active indicator rules and update healthcare_indicator_ids.

        Always uses sudo() so that:
        - Indicator records are readable regardless of the calling user's group
        - Child relation fields are readable even when restricted by groups
        - Writing healthcare_indicator_ids succeeds despite any access restrictions
        """
        indicators = self.env['employee.healthcare.indicator'].sudo().search(
            [('active', '=', True)]
        )
        for record in self.sudo():
            active = indicators.filtered(lambda ind: ind._matches(record))
            if record.healthcare_indicator_ids != active:
                record.healthcare_indicator_ids = active
        return True

    def action_confirm_verified(self):
        """Mark this healthcare record as verified at the current datetime.

        Called from the frontend after the employee clicks 'Confirm' in the
        save-confirmation dialog to assert the profile is up-to-date.
        """
        self.ensure_one()
        self.write({'last_verified': fields.Datetime.now()})
        return True

    def action_print_care_profile(self):
        """Download the employee Care Profile PDF directly."""
        self.ensure_one()
        return self.env.ref(
            'employee_healthcare.action_report_employee_care_profile'
        ).report_action(self, config=False)

    @api.model
    def _ensure_all_employee_records(self):
        """Create a healthcare record for every employee that does not have one.

        Called via <function> in data XML on every install/upgrade so that the
        employee and healthcare tables are always kept in sync.
        """
        all_employees = self.env['hr.employee'].sudo().search([])
        existing_ids = set(
            self.sudo().search([]).mapped('employee_id').ids
        )
        missing = all_employees.filtered(lambda e: e.id not in existing_ids)
        if missing:
            self.sudo().create([{'employee_id': emp.id} for emp in missing])

    @api.model
    def action_get_my_profile(self):
        """Navigate to the current user's own healthcare record.

        Returns the *named* act_window action (which carries path='healthcare')
        with res_id set to the current user's record.  Because the action has a
        database id the web client resolves the path attribute and produces the
        clean URL /odoo/healthcare/<id> without any HTTP redirect.
        """
        employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1,
        )
        healthcare = self.search(
            [('employee_id', '=', employee.id)], limit=1,
        ) if employee else self.browse()

        if not healthcare and employee:
            healthcare = self.sudo().create({'employee_id': employee.id})

        action = self.env.ref(
            'employee_healthcare.action_hr_employee_healthcare'
        ).read()[0]

        if healthcare:
            action['res_id'] = healthcare.id
            action['view_mode'] = 'form'
            action['views'] = [(
                self.env.ref(
                    'employee_healthcare.view_employee_healthcare_form'
                ).id, 'form',
            )]

        return action

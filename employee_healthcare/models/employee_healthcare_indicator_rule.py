import datetime
from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval


_RELATION_FIELDS = [
    ('healthcare_medication_ids', 'Medications'),
    ('healthcare_allergy_ids', 'Allergies'),
    ('healthcare_alert_ids', 'Health Alerts'),
    ('healthcare_directive_ids', 'Directives / Proxies'),
]

_EMPLOYEE_FIELDS = [
    ('medicare_number', 'Medicare Number'),
    ('medicare_expiry', 'Medicare Expiry'),
    ('private_health_insurer_id', 'Private Health Insurer'),
    ('private_health_member_number', 'Private Health Member Number'),
    ('ambulance_provider_id', 'Ambulance Provider'),
    ('ambulance_membership_number', 'Ambulance Membership Number'),
    ('ambulance_membership_expiry', 'Ambulance Membership Expiry'),
]

_DATE_FIELDS = [
    ('medicare_expiry', 'Medicare Expiry'),
    ('ambulance_membership_expiry', 'Ambulance Membership Expiry'),
    ('last_verified', 'Last Verified'),
]


class EmployeeHealthcareIndicatorRule(models.Model):
    _name = 'employee.healthcare.indicator.rule'
    _description = 'Healthcare Indicator Rule'
    _order = 'indicator_id, sequence'

    indicator_id = fields.Many2one(
        'employee.healthcare.indicator', string='Indicator',
        required=True, ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(
        string='Rule Description', required=True,
        help='Plain-language description of what this rule checks.',
    )
    rule_type = fields.Selection([
        ('relation', 'Related Records'),
        ('field', 'Employee Field Value'),
        ('date', 'Date Condition'),
    ], string='Rule Type', required=True, default='relation')

    # ── Relation rule ────────────────────────────────────────────────────
    relation_field = fields.Selection(
        _RELATION_FIELDS, string='Relationship',
        help='Which One2many relationship on the employee to inspect.',
    )
    relation_condition = fields.Selection([
        ('exists', 'Any record exists'),
        ('not_exists', 'No records exist'),
        ('any_match', 'Any record matches filter'),
        ('none_match', 'No records match filter'),
        ('all_match', 'All records match filter'),
        ('count_gt', 'Count is greater than'),
        ('count_gte', 'Count is at least'),
        ('count_eq', 'Count equals'),
        ('count_lt', 'Count is less than'),
    ], string='Condition')
    relation_domain = fields.Char(
        string='Filter (domain)',
        help='Optional Odoo domain to filter related records before applying the condition.\n'
             'Example: [("is_critical", "=", True)]\n'
             'Leave blank to match all records in the relationship.',
    )
    relation_count_threshold = fields.Integer(
        string='Count Threshold', default=1,
        help='Used by the count_gt / count_gte / count_eq / count_lt conditions.',
    )

    # ── Field rule ───────────────────────────────────────────────────────
    employee_field = fields.Selection(_EMPLOYEE_FIELDS, string='Employee Field')
    field_operator = fields.Selection([
        ('set', 'Is set (not empty)'),
        ('not_set', 'Is not set (empty)'),
        ('equals', 'Equals'),
        ('not_equals', 'Does not equal'),
    ], string='Operator')
    field_value = fields.Char(
        string='Value',
        help='For relational fields enter the database ID of the record (integer).\n'
             'For text fields enter the exact string to compare.\n'
             'For Boolean fields enter True or False.',
    )

    # ── Date rule ────────────────────────────────────────────────────────
    date_field = fields.Selection(_DATE_FIELDS, string='Date Field')
    date_condition = fields.Selection([
        ('is_set', 'Is set'),
        ('is_not_set', 'Is not set'),
        ('older_than_days', 'Older than N days ago'),
        ('within_days', 'Within the last N days'),
        ('expires_within_days', 'Expires within N days'),
        ('already_expired', 'Already expired'),
    ], string='Date Condition')
    date_threshold_days = fields.Integer(
        string='Days', default=30,
        help='Number of days used for the date conditions.',
    )

    # ── Re-evaluate employees when rules change ──────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped('indicator_id')._reeval_all_employees()
        return records

    def write(self, vals):
        result = super().write(vals)
        self.mapped('indicator_id')._reeval_all_employees()
        return result

    def unlink(self):
        indicators = self.mapped('indicator_id')
        result = super().unlink()
        indicators._reeval_all_employees()
        return result

    # ── Evaluation ───────────────────────────────────────────────────────
    def _evaluate(self, employee):
        """Evaluate this rule against an hr.employee record. Returns True or False."""
        self.ensure_one()
        try:
            if self.rule_type == 'relation':
                return self._eval_relation(employee)
            if self.rule_type == 'field':
                return self._eval_field(employee)
            if self.rule_type == 'date':
                return self._eval_date(employee)
        except Exception:
            return False
        return False

    def _eval_relation(self, employee):
        if not self.relation_field or not self.relation_condition:
            return False
        related = getattr(employee, self.relation_field)

        filtered = related
        if self.relation_domain and self.relation_domain.strip():
            try:
                domain = safe_eval(self.relation_domain)
                filtered = related.filtered_domain(domain)
            except Exception:
                filtered = related

        cond = self.relation_condition
        if cond == 'exists':
            return bool(related)
        if cond == 'not_exists':
            return not related
        if cond == 'any_match':
            return bool(filtered)
        if cond == 'none_match':
            return not filtered
        if cond == 'all_match':
            return bool(related) and len(filtered) == len(related)
        if cond == 'count_gt':
            return len(filtered) > self.relation_count_threshold
        if cond == 'count_gte':
            return len(filtered) >= self.relation_count_threshold
        if cond == 'count_eq':
            return len(filtered) == self.relation_count_threshold
        if cond == 'count_lt':
            return len(filtered) < self.relation_count_threshold
        return False

    def _eval_field(self, employee):
        if not self.employee_field or not self.field_operator:
            return False
        value = getattr(employee, self.employee_field)
        op = self.field_operator

        if op == 'set':
            return bool(value)
        if op == 'not_set':
            return not value

        raw = self.field_value or ''
        if hasattr(value, 'id'):
            try:
                match = value.id == int(raw)
            except (ValueError, TypeError):
                match = (value.name or '') == raw
        elif isinstance(value, bool):
            match = value == (raw.strip().lower() in ('true', '1', 'yes'))
        else:
            match = str(value or '') == raw

        return match if op == 'equals' else not match

    def _eval_date(self, employee):
        if not self.date_field or not self.date_condition:
            return False
        value = getattr(employee, self.date_field)
        cond = self.date_condition

        if cond == 'is_set':
            return bool(value)
        if cond == 'is_not_set':
            return not value
        if not value:
            return False

        today = datetime.date.today()
        # last_verified is a Datetime; the others are Date — normalise to date
        value_date = value.date() if isinstance(value, datetime.datetime) else value
        delta = (today - value_date).days

        if cond == 'older_than_days':
            return delta > self.date_threshold_days
        if cond == 'within_days':
            return 0 <= delta <= self.date_threshold_days
        if cond == 'expires_within_days':
            # value is in the future but within N days
            days_until = (value_date - today).days
            return 0 <= days_until <= self.date_threshold_days
        if cond == 'already_expired':
            return value_date < today
        return False

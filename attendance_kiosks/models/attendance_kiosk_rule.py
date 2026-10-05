from odoo import api, fields, models


class AttendanceKioskRule(models.Model):
    _name = 'attendance.kiosk.rule'
    _description = 'Attendance Kiosk Sign In Rule'
    _order = 'kiosk_id, sequence, id'

    kiosk_id = fields.Many2one('attendance.kiosk', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='kiosk_id.company_id', store=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    name = fields.Char(string='Rule', required=True)
    rule_type = fields.Selection(
        [('require', 'Must meet requirements'), ('deny', 'Refuse sign in')],
        string='Action', default='require', required=True,
        help='Must meet requirements: the employees this rule applies to can only sign in '
             'if they meet the requirements below.\n'
             'Refuse sign in: the employees this rule applies to cannot sign in at this kiosk.',
    )
    applies_domain = fields.Char(
        string='Applies To', default='[]',
        help='The employees this rule applies to. Leave empty for everyone.',
    )
    requirement_domain = fields.Char(
        string='Employee Requirements', default='[]',
        help='The employees this rule applies to must also match this filter, e.g. have a '
             'badge, a particular job position or tag.',
    )
    required_course_ids = fields.Many2many(
        'lms.course', 'attendance_kiosk_rule_required_course_rel', 'rule_id', 'course_id',
        string='Must Hold All Of',
        help='Learning capabilities the employee must currently hold (completed and unexpired).',
    )
    any_course_ids = fields.Many2many(
        'lms.course', 'attendance_kiosk_rule_any_course_rel', 'rule_id', 'course_id',
        string='Must Hold At Least One Of',
        help='The employee must currently hold at least one of these Learning capabilities.',
    )
    message = fields.Char(
        string='Message When Refused',
        help='Shown on the kiosk when this rule stops someone signing in. '
             'Leave empty to show the rule name and what is missing.',
    )

    @api.constrains('applies_domain', 'requirement_domain')
    def _check_domains(self):
        for rule in self:
            rule.kiosk_id._kiosk_validate_domain(rule.applies_domain)
            rule.kiosk_id._kiosk_validate_domain(rule.requirement_domain)

from odoo import api, fields, models


class InjuryRtwPlan(models.Model):
    _name = 'injury.rtw.plan'
    _description = 'Return to Work Plan'
    _inherit = ['mail.thread']
    _order = 'plan_date desc'
    _rec_name = 'display_name'

    case_id = fields.Many2one('injury.rtw.case', string='Case', required=True, ondelete='cascade', index=True)
    plan_date = fields.Date('Plan Date', required=True, default=fields.Date.today)
    version = fields.Char('Version / Reference', default='v1')
    state = fields.Selection([
        ('draft',     'Draft'),
        ('active',    'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, tracking=True)
    start_date = fields.Date('Plan Start Date', required=True)
    end_date = fields.Date('Plan End Date')
    approved_by_id = fields.Many2one('res.users', string='Approved By', domain=[('share', '=', False)])
    approval_date = fields.Date('Approval Date')
    treating_doctor = fields.Char('Treating Doctor')
    goals = fields.Text('Goals / Objectives')
    notes = fields.Text('Additional Notes')
    line_ids = fields.One2many('injury.rtw.plan.line', 'plan_id', string='Plan Phases')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'injury_rtw_plan_ir_attachment_rel',
        'plan_id', 'attachment_id',
        string='Attachments',
    )

    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('version', 'start_date')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.version} \u2014 {rec.start_date}" if rec.start_date else rec.version or 'Draft Plan'

    def action_activate(self):
        self.state = 'active'

    def action_complete(self):
        self.state = 'completed'

    def action_cancel(self):
        self.state = 'cancelled'


class InjuryRtwPlanLine(models.Model):
    _name = 'injury.rtw.plan.line'
    _description = 'RTW Plan Phase / Period'
    _order = 'sequence, id'

    plan_id = fields.Many2one('injury.rtw.plan', string='Plan', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    phase_label = fields.Char('Phase / Week', required=True)
    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    daily_hours = fields.Float('Daily Hours', digits=(4, 1))
    days_per_week = fields.Integer('Days per Week')
    duties = fields.Text('Duties / Tasks')
    restrictions = fields.Text('Restrictions / Limitations')
    notes = fields.Text('Notes')

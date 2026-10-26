from odoo import api, fields, models


class AdvancedProjectBudgetCategory(models.Model):
    """What a budget line is for (Labour, Materials, Travel, ...)."""
    _name = 'advanced.project.budget.category'
    _description = 'Project Budget Category'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique (name)', 'A budget category with this name already exists.')


class AdvancedProjectBudgetLine(models.Model):
    """One part of a project's budget: hours allocated and money budgeted,
    optionally for one phase. The project's budget is the sum of its lines."""
    _name = 'advanced.project.budget.line'
    _description = 'Project Budget Line'
    _order = 'project_id, sequence, id'

    project_id = fields.Many2one(
        'advanced.project', string='Project', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='project_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='project_id.currency_id')
    sequence = fields.Integer(default=10)
    category_id = fields.Many2one('advanced.project.budget.category', string='Category', index=True)
    name = fields.Char('Description')
    phase_id = fields.Many2one(
        'advanced.project.phase', string='Phase', index=True, ondelete='set null',
        domain="[('project_id', '=', project_id)]")
    allocated_hours = fields.Float('Allocated Hours')
    amount = fields.Monetary('Budget', currency_field='currency_id')
    spent_amount = fields.Monetary(
        'Spent', currency_field='currency_id', help='What has been spent against this line so far.')
    remaining_amount = fields.Monetary('Remaining', currency_field='currency_id', compute='_compute_remaining_amount')

    @api.depends('amount', 'spent_amount')
    def _compute_remaining_amount(self):
        for line in self:
            line.remaining_amount = line.amount - line.spent_amount

    def _copy_budget_values(self, project, phase_map):
        """Values to recreate this line on ``project`` (templates, copies);
        nothing is spent on the new project yet."""
        self.ensure_one()
        return {
            'project_id': project.id,
            'sequence': self.sequence,
            'category_id': self.category_id.id,
            'name': self.name,
            'phase_id': phase_map[self.phase_id.id].id if self.phase_id.id in phase_map else False,
            'allocated_hours': self.allocated_hours,
            'amount': self.amount,
        }


class AdvancedProject(models.Model):
    _inherit = 'advanced.project'

    # Budgets are for the company's eyes: customers never see them.
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True, groups='base.group_user',
        default=lambda self: self.env.company.currency_id)
    budget_line_ids = fields.One2many(
        'advanced.project.budget.line', 'project_id', string='Budget Lines', copy=False, groups='base.group_user')
    allocated_hours = fields.Float(
        'Allocated Hours', compute='_compute_budget', store=True, groups='base.group_user',
        help='Hours allocated to the project: the total of its budget lines.')
    budget_amount = fields.Monetary(
        'Budget', currency_field='currency_id', compute='_compute_budget', store=True, groups='base.group_user',
        help='Money budgeted for the project: the total of its budget lines.')
    spent_amount = fields.Monetary(
        'Spent', currency_field='currency_id', compute='_compute_budget', store=True, groups='base.group_user')
    remaining_budget = fields.Monetary(
        'Remaining Budget', currency_field='currency_id', compute='_compute_budget', store=True,
        groups='base.group_user')
    budget_used = fields.Float(
        'Budget Used (%)', compute='_compute_budget', store=True, groups='base.group_user')
    planned_hours = fields.Float(
        'Planned on Tasks', compute='_compute_planned_hours', groups='base.group_user',
        help="The total of the tasks' Planned Hours.")

    @api.depends('budget_line_ids.allocated_hours', 'budget_line_ids.amount', 'budget_line_ids.spent_amount')
    def _compute_budget(self):
        for project in self:
            lines = project.budget_line_ids
            project.allocated_hours = sum(lines.mapped('allocated_hours'))
            project.budget_amount = sum(lines.mapped('amount'))
            project.spent_amount = sum(lines.mapped('spent_amount'))
            project.remaining_budget = project.budget_amount - project.spent_amount
            project.budget_used = (100 * project.spent_amount / project.budget_amount) if project.budget_amount else 0.0

    @api.depends('task_ids.planned_hours')
    def _compute_planned_hours(self):
        for project in self:
            project.planned_hours = sum(project.task_ids.mapped('planned_hours'))

    def _copy_plan_from(self, source, day_shift=0):
        super()._copy_plan_from(source, day_shift=day_shift)
        source = source.sudo()
        if source.budget_line_ids:
            # the phases were just copied in the source's order
            phase_map = {old.id: new for old, new in zip(source.phase_ids, self.phase_ids)}
            self.currency_id = source.currency_id
            self.env['advanced.project.budget.line'].create([
                line._copy_budget_values(self, phase_map) for line in source.budget_line_ids])

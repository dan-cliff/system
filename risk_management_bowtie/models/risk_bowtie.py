from odoo import api, fields, models
from odoo.exceptions import AccessError


class RiskBowtieBarrierType(models.Model):
    _name = 'risk.bowtie.barrier.type'
    _description = 'Bowtie Barrier Type'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    description = fields.Text()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'A barrier type with this name already exists.',
    )


class RiskBowtieBarrierEffectiveness(models.Model):
    _name = 'risk.bowtie.barrier.effectiveness'
    _description = 'Bowtie Barrier Effectiveness'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    description = fields.Text()
    color = fields.Char(
        string='Colour', default='#9e9e9e',
        help='Hex colour shown on barriers with this effectiveness in the bowtie diagram.',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'A barrier effectiveness with this name already exists.',
    )


class RiskBowtieMixin(models.AbstractModel):
    """Bowtie records are part of their Risk: changing one needs edit access to that Risk.

    The Risk is the Risk Assessment line (Risks access) or Risk Template line (Risk
    Templates access) in ``assessment_line_id`` / ``template_line_id``, so a user who can
    only view a Risk can't change its bowtie, and Risk Assessments' Risks and Risk
    Templates' Risks keep their separate permissions.
    """
    _name = 'risk.bowtie.mixin'
    _description = 'Bowtie Record Access'

    def _check_risk_access(self, operation):
        if self.env.su:
            return
        for lines in (self.assessment_line_id, self.template_line_id):
            if not lines:
                continue
            # Adding to a Risk that is being created with its bowtie only needs Create.
            if lines.has_access('write') or (operation == 'create' and lines.has_access('create')):
                continue
            raise AccessError(
                "You can't change the bowtie of %s because you can't edit that Risk."
                % ', '.join(lines.mapped('name'))
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_risk_access('create')
        return records

    def write(self, vals):
        self._check_risk_access('write')
        result = super().write(vals)
        self._check_risk_access('write')
        return result

    def unlink(self):
        self._check_risk_access('unlink')
        return super().unlink()


class RiskBowtieThreat(models.Model):
    _name = 'risk.bowtie.threat'
    _inherit = ['risk.bowtie.mixin']
    _description = 'Bowtie Threat'
    _order = 'sequence, id'

    name = fields.Char(string='Threat', required=True)
    description = fields.Text()
    sequence = fields.Integer(default=10)
    assessment_line_id = fields.Many2one('risk.assessment.line', ondelete='cascade', index=True)
    template_line_id = fields.Many2one('risk.template.line', ondelete='cascade', index=True)
    barrier_ids = fields.One2many(
        'risk.bowtie.barrier', 'threat_id', string='Preventive Barriers', copy=True,
    )

    def _bowtie_copy_vals(self):
        self.ensure_one()
        return {
            'sequence': self.sequence,
            'name': self.name,
            'description': self.description,
            'barrier_ids': [(0, 0, barrier._bowtie_copy_vals()) for barrier in self.barrier_ids],
        }


class RiskBowtieConsequence(models.Model):
    _name = 'risk.bowtie.consequence'
    _inherit = ['risk.bowtie.mixin']
    _description = 'Bowtie Consequence'
    _order = 'sequence, id'

    name = fields.Char(string='Consequence', required=True)
    description = fields.Text()
    sequence = fields.Integer(default=10)
    consequence_id = fields.Many2one(
        'risk.consequence', string='Severity',
        help='How severe this outcome would be, using the Risk Matrix consequence bands.',
    )
    assessment_line_id = fields.Many2one('risk.assessment.line', ondelete='cascade', index=True)
    template_line_id = fields.Many2one('risk.template.line', ondelete='cascade', index=True)
    barrier_ids = fields.One2many(
        'risk.bowtie.barrier', 'consequence_id', string='Recovery Barriers', copy=True,
    )

    def _bowtie_copy_vals(self):
        self.ensure_one()
        return {
            'sequence': self.sequence,
            'name': self.name,
            'description': self.description,
            'consequence_id': self.consequence_id.id,
            'barrier_ids': [(0, 0, barrier._bowtie_copy_vals()) for barrier in self.barrier_ids],
        }


class RiskBowtieBarrier(models.Model):
    _name = 'risk.bowtie.barrier'
    _inherit = ['risk.bowtie.mixin']
    _description = 'Bowtie Barrier'
    _order = 'sequence, id'

    name = fields.Char(string='Barrier', required=True)
    description = fields.Text()
    sequence = fields.Integer(default=10)
    control_id = fields.Many2one(
        'risk.control', string='Library Control',
        help='Optionally link this barrier to a Control in the Controls library.',
    )
    barrier_type_id = fields.Many2one('risk.bowtie.barrier.type', string='Barrier Type')
    effectiveness_id = fields.Many2one('risk.bowtie.barrier.effectiveness', string='Effectiveness')
    effectiveness_color = fields.Char(related='effectiveness_id.color', readonly=True)
    accountable = fields.Char(
        string='Accountable',
        help='The person or role responsible for keeping this barrier in place, e.g. Activity Leader.',
    )

    # Exactly one parent: a threat (preventive), a consequence (recovery) or an
    # escalation factor (a barrier protecting another barrier).
    threat_id = fields.Many2one('risk.bowtie.threat', ondelete='cascade', index=True)
    consequence_id = fields.Many2one('risk.bowtie.consequence', ondelete='cascade', index=True)
    escalation_factor_id = fields.Many2one(
        'risk.bowtie.escalation.factor', ondelete='cascade', index=True,
    )
    barrier_side = fields.Selection(
        [('preventive', 'Preventive'), ('recovery', 'Recovery'), ('escalation', 'Escalation Factor')],
        compute='_compute_root', store=True,
    )
    escalation_factor_ids = fields.One2many(
        'risk.bowtie.escalation.factor', 'barrier_id', string='Escalation Factors', copy=True,
        help='Conditions that could make this barrier fail or less effective.',
    )

    # The Risk this barrier ultimately belongs to - used by the record rules.
    assessment_line_id = fields.Many2one(
        'risk.assessment.line', compute='_compute_root', store=True, index=True,
    )
    template_line_id = fields.Many2one(
        'risk.template.line', compute='_compute_root', store=True, index=True,
    )

    @api.depends(
        'threat_id.assessment_line_id', 'threat_id.template_line_id',
        'consequence_id.assessment_line_id', 'consequence_id.template_line_id',
        'escalation_factor_id.barrier_id.threat_id.assessment_line_id',
        'escalation_factor_id.barrier_id.threat_id.template_line_id',
        'escalation_factor_id.barrier_id.consequence_id.assessment_line_id',
        'escalation_factor_id.barrier_id.consequence_id.template_line_id',
    )
    def _compute_root(self):
        for barrier in self:
            if barrier.threat_id:
                parent, side = barrier.threat_id, 'preventive'
            elif barrier.consequence_id:
                parent, side = barrier.consequence_id, 'recovery'
            else:
                protected = barrier.escalation_factor_id.barrier_id
                parent, side = protected.threat_id or protected.consequence_id, 'escalation'
            barrier.barrier_side = side
            barrier.assessment_line_id = parent.assessment_line_id
            barrier.template_line_id = parent.template_line_id

    @api.onchange('control_id')
    def _onchange_control_id(self):
        if self.control_id and not self.name:
            self.name = self.control_id.name

    def _bowtie_copy_vals(self):
        self.ensure_one()
        return {
            'sequence': self.sequence,
            'name': self.name,
            'description': self.description,
            'control_id': self.control_id.id,
            'barrier_type_id': self.barrier_type_id.id,
            'effectiveness_id': self.effectiveness_id.id,
            'accountable': self.accountable,
            'escalation_factor_ids': [
                (0, 0, factor._bowtie_copy_vals()) for factor in self.escalation_factor_ids
            ],
        }


class RiskBowtieEscalationFactor(models.Model):
    _name = 'risk.bowtie.escalation.factor'
    _inherit = ['risk.bowtie.mixin']
    _description = 'Bowtie Escalation Factor'
    _order = 'sequence, id'

    name = fields.Char(string='Escalation Factor', required=True)
    description = fields.Text()
    sequence = fields.Integer(default=10)
    barrier_id = fields.Many2one(
        'risk.bowtie.barrier', string='Barrier', required=True, ondelete='cascade', index=True,
    )
    barrier_ids = fields.One2many(
        'risk.bowtie.barrier', 'escalation_factor_id', string='Escalation Factor Barriers', copy=True,
        help='Barriers that stop this escalation factor from weakening the main barrier.',
    )
    assessment_line_id = fields.Many2one(
        'risk.assessment.line', compute='_compute_root', store=True, index=True,
    )
    template_line_id = fields.Many2one(
        'risk.template.line', compute='_compute_root', store=True, index=True,
    )

    @api.depends(
        'barrier_id.threat_id.assessment_line_id', 'barrier_id.threat_id.template_line_id',
        'barrier_id.consequence_id.assessment_line_id', 'barrier_id.consequence_id.template_line_id',
    )
    def _compute_root(self):
        for factor in self:
            parent = factor.barrier_id.threat_id or factor.barrier_id.consequence_id
            factor.assessment_line_id = parent.assessment_line_id
            factor.template_line_id = parent.template_line_id

    def _bowtie_copy_vals(self):
        self.ensure_one()
        return {
            'sequence': self.sequence,
            'name': self.name,
            'description': self.description,
            # Escalation factor barriers don't carry escalation factors of their own.
            'barrier_ids': [
                (0, 0, dict(barrier._bowtie_copy_vals(), escalation_factor_ids=[]))
                for barrier in self.barrier_ids
            ],
        }

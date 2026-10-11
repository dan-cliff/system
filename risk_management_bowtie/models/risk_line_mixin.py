import base64

from odoo import fields, models

from .risk_bowtie_svg import render_bowtie_svg


class RiskLineMixin(models.AbstractModel):
    _inherit = 'risk.line.mixin'

    # Bowtie analysis: the Unwanted Event is shown as the bowtie's Hazard and the Risk
    # itself is the Top Event. Each concrete model adds its own bowtie_threat_ids /
    # bowtie_consequence_ids.
    unwanted_event = fields.Text(
        string='Hazard',
        help='Something in or around the activity with the potential to cause harm, which is '
             'normally present and needed for the activity, e.g. "Working at height". Shown '
             'as the Hazard on the bowtie diagram, with the Risk as its Top Event.',
    )
    has_bowtie = fields.Boolean(compute='_compute_has_bowtie')

    # Filling in one risk by AI now includes its bowtie, which roughly doubles the answer.
    _ai_risk_max_tokens = 8192
    _ai_risk_timeout = 300

    def _compute_has_bowtie(self):
        for line in self:
            line.has_bowtie = bool(line.bowtie_threat_ids or line.bowtie_consequence_ids)

    def get_bowtie_svg(self):
        """The bowtie diagram as SVG markup - shown by the Bowtie Diagram dialog and the PDF."""
        self.ensure_one()
        return render_bowtie_svg(self)

    def _bowtie_report_image(self, max_aspect=0.47, full_width=1700):
        """Data URI and width (%) of the bowtie as an image for the PDF appendix.

        An <img> keeps the diagram's proportions under wkhtmltopdf. A diagram
        ``full_width`` px wide fills the page and smaller ones keep the same
        scale; tall diagrams are narrowed so the whole bowtie fits on one
        landscape page.
        """
        self.ensure_one()
        svg = str(self.get_bowtie_svg())
        viewbox = svg.split('viewBox="', 1)[1].split('"', 1)[0].split()
        width, height = float(viewbox[2]), float(viewbox[3])
        aspect = height / width if width else 1
        width_pct = min(100, 100 * width / full_width, 100 * max_aspect / aspect if aspect else 100)
        return {
            'src': 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode(),
            'width': round(width_pct, 1),
        }

    def action_open_bowtie(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'risk_bowtie_diagram',
            'name': 'Bowtie: %s' % (self.name or ''),
            'target': 'new',
            'params': {'res_model': self._name, 'res_id': self.id},
            'context': {'dialog_size': 'extra-large'},
        }

    def _bowtie_copy_vals(self):
        """Values recreating this risk's bowtie on another risk line."""
        self.ensure_one()
        return {
            'bowtie_threat_ids': [(0, 0, threat._bowtie_copy_vals()) for threat in self.bowtie_threat_ids],
            'bowtie_consequence_ids': [
                (0, 0, consequence._bowtie_copy_vals()) for consequence in self.bowtie_consequence_ids
            ],
        }

    def _ai_risk_prompt(self):
        prompt = super()._ai_risk_prompt()
        barrier_types = self.env['risk.bowtie.barrier.type'].search([]).mapped('name')
        effectiveness = self.env['risk.bowtie.barrier.effectiveness'].search([]).mapped('name')
        consequences = self.env['risk.consequence'].search([], order='sequence, value').mapped('name')
        return prompt + self._ai_build_bowtie_prompt(barrier_types, effectiveness, consequences)

    def _ai_risk_empty_fields(self):
        names = super()._ai_risk_empty_fields()
        return names + [name for name in ('bowtie_threat_ids', 'bowtie_consequence_ids') if not self[name]]

    def _ai_risk_vals(self, data):
        vals = super()._ai_risk_vals(data)
        bowtie = self._ai_bowtie_vals(data.get('bowtie'))
        empty = self._ai_risk_empty_fields()
        for field_name in ('bowtie_threat_ids', 'bowtie_consequence_ids'):
            if field_name in empty and bowtie.get(field_name):
                vals[field_name] = bowtie[field_name]
        return vals

    def _ai_build_bowtie_prompt(self, barrier_types, effectiveness, consequences):
        return (
            "\n\nAlso give each risk object a \"bowtie\" key holding its bowtie analysis. In the bowtie, "
            "the risk's unwanted_event is the Hazard (something with the potential to cause harm "
            "that is normally present in the activity, e.g. 'Working at height'), so write "
            "unwanted_event that way, and the risk's name is the Top Event (the moment control "
            "over the hazard is lost). Identify 2-4 Threats (causes that could lead to the Top Event), "
            "each with 1-3 Preventive Barriers that stop the threat leading to the Top Event; "
            "and 2-4 Consequences (outcomes of the Top Event), each with 1-3 Recovery Barriers "
            "that reduce or stop the consequence. Only where a barrier could realistically be "
            "undermined, add Escalation Factors (conditions that make that barrier fail), each "
            "with 1-2 Escalation Factor Barriers. Barriers must be specific and effective on "
            "their own, not vague (e.g. 'Supervision' alone is too vague). Reuse Control names "
            "from our library above as barrier names where they fit.\n\n"
            "Barrier types (choose exactly one of these names for each barrier's \"type\"): "
            + ', '.join(barrier_types or ['(none configured)']) + "\n\n"
            "Barrier effectiveness (choose exactly one of these names, for how effective the "
            "barrier would be once implemented): " + ', '.join(effectiveness or ['(none configured)']) + "\n\n"
            "Each consequence's \"severity\" must be one of the Consequence band names above.\n\n"
            "The \"bowtie\" key has this exact shape:\n"
            '{"threats": [{"name": "threat", "barriers": [BARRIER, ...]}], '
            '"consequences": [{"name": "consequence", "severity": "Consequence band name", '
            '"barriers": [BARRIER, ...]}]}\n'
            "where each BARRIER is:\n"
            '{"name": "barrier", "type": "Barrier type name", "effectiveness": "Effectiveness name", '
            '"accountable": "role responsible, e.g. Activity Leader", '
            '"escalation_factors": [{"name": "escalation factor", "barriers": [{"name": "barrier", '
            '"type": "Barrier type name", "effectiveness": "Effectiveness name", '
            '"accountable": "role"}]}]}\n'
            "Use an empty escalation_factors list where there are none."
        )

    def _ai_bowtie_vals(self, bowtie):
        """Risk line values for the bowtie part of one AI-generated risk."""
        if not isinstance(bowtie, dict):
            return {}
        BarrierType = self.env['risk.bowtie.barrier.type']
        Effectiveness = self.env['risk.bowtie.barrier.effectiveness']
        Consequence = self.env['risk.consequence']
        Control = self.env['risk.control']

        def text(value):
            return value.strip() if isinstance(value, str) else ''

        def items(value):
            return [item for item in (value or []) if isinstance(item, dict) and text(item.get('name'))] \
                if isinstance(value, list) else []

        def find(Model, name):
            name = text(name)
            return Model.search([('name', '=ilike', name)], limit=1).id if name else False

        def barrier_vals(barrier, sequence, with_escalation=True):
            name = text(barrier.get('name'))
            vals = {
                'sequence': sequence,
                'name': name,
                # Link to the library only when the control already exists: creating new
                # controls here would trigger a slow AI description call for each barrier.
                'control_id': find(Control, name),
                'barrier_type_id': find(BarrierType, barrier.get('type')),
                'effectiveness_id': find(Effectiveness, barrier.get('effectiveness')),
                'accountable': text(barrier.get('accountable')),
            }
            if with_escalation:
                vals['escalation_factor_ids'] = [
                    (0, 0, {
                        'sequence': (index + 1) * 10,
                        'name': text(factor.get('name')),
                        'barrier_ids': [
                            (0, 0, barrier_vals(sub, (sub_index + 1) * 10, with_escalation=False))
                            for sub_index, sub in enumerate(items(factor.get('barriers')))
                        ],
                    })
                    for index, factor in enumerate(items(barrier.get('escalation_factors')))
                ]
            return vals

        return {
            'bowtie_threat_ids': [
                (0, 0, {
                    'sequence': (index + 1) * 10,
                    'name': text(threat.get('name')),
                    'barrier_ids': [
                        (0, 0, barrier_vals(barrier, (b_index + 1) * 10))
                        for b_index, barrier in enumerate(items(threat.get('barriers')))
                    ],
                })
                for index, threat in enumerate(items(bowtie.get('threats')))
            ],
            'bowtie_consequence_ids': [
                (0, 0, {
                    'sequence': (index + 1) * 10,
                    'name': text(consequence.get('name')),
                    'consequence_id': find(Consequence, consequence.get('severity')),
                    'barrier_ids': [
                        (0, 0, barrier_vals(barrier, (b_index + 1) * 10))
                        for b_index, barrier in enumerate(items(consequence.get('barriers')))
                    ],
                })
                for index, consequence in enumerate(items(bowtie.get('consequences')))
            ],
        }

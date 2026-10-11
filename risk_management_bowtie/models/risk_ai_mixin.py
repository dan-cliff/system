from odoo import models


class RiskAiMixin(models.AbstractModel):
    _inherit = 'risk.ai.mixin'

    # A bowtie per risk roughly doubles the response, so allow a longer answer.
    _ai_max_tokens = 16000
    _ai_timeout = 300

    def _ai_build_prompt(self, existing_types, existing_subtypes, existing_controls, likelihoods, consequences):
        prompt = super()._ai_build_prompt(
            existing_types, existing_subtypes, existing_controls, likelihoods, consequences,
        )
        barrier_types = self.env['risk.bowtie.barrier.type'].search([]).mapped('name')
        effectiveness = self.env['risk.bowtie.barrier.effectiveness'].search([]).mapped('name')
        return prompt + self._ai_build_bowtie_prompt(barrier_types, effectiveness, consequences)

    def _ai_build_bowtie_prompt(self, barrier_types, effectiveness, consequences):
        return (
            "\n\nAlso give every risk object a \"bowtie\" key holding its bowtie analysis. Treat the risk's "
            "unwanted_event as the bowtie's Top Event (the moment control over the hazard is "
            "lost). Identify the Hazard; 2-4 Threats (causes that could lead to the Top Event), "
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
            '{"hazard": "the hazard", '
            '"threats": [{"name": "threat", "barriers": [BARRIER, ...]}], '
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

    def _ai_line_vals(self, risk, vals):
        vals = super()._ai_line_vals(risk, vals)
        vals.update(self._ai_bowtie_vals(risk.get('bowtie')))
        return vals

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
            'bowtie_hazard': text(bowtie.get('hazard')),
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

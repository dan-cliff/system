from odoo import api, fields, models
from odoo.exceptions import UserError

from .risk_ai_mixin import ai_parse_json, ai_request_text


class RiskLineMixin(models.AbstractModel):
    _name = 'risk.line.mixin'
    _description = 'Risk Line Mixin'

    # XML ID of this concrete model's own form view, set by each model that
    # inherits this mixin. Without this, "open full record" navigation (e.g.
    # the expand icon on a one2many dialog) has no view to resolve to and
    # falls back to a bare, auto-generated form showing every raw field.
    _form_view_xmlid = None
    # Field linking a concrete risk line to its Risk Assessment / Risk Template (set by
    # each concrete model), whose Summary of Activity gives the AI its context.
    _ai_parent_field = None
    # The concrete model's actions field, which "Fill Empty Fields by AI" also fills.
    _ai_actions_field = None
    # Claude request limits for generating one risk; extensions can raise them.
    _ai_risk_max_tokens = 4096
    _ai_risk_timeout = 180

    name = fields.Text(string='Risk', required=True)
    unwanted_event = fields.Text(string='Unwanted Event')
    description = fields.Text()
    control_ids = fields.Many2many('risk.control', string='Controls')
    control_summary = fields.Text(string='Controls Summary')

    risk_type_id = fields.Many2one('risk.type', string='Risk Type')
    risk_subtype_id = fields.Many2one(
        'risk.subtype', string='Risk Subtype',
        domain="[('risk_type_id', '=', risk_type_id)]",
    )

    inherent_likelihood_id = fields.Many2one('risk.likelihood', string='Inherent Likelihood')
    inherent_consequence_id = fields.Many2one('risk.consequence', string='Inherent Consequence')
    inherent_risk_score_id = fields.Many2one(
        'risk.score', string='Inherent Risk Matrix Cell', compute='_compute_risk_score_ids', store=True,
    )
    inherent_severity_id = fields.Many2one(
        related='inherent_risk_score_id.severity_id', string='Inherent Severity', store=True, readonly=True,
    )
    inherent_score = fields.Integer(related='inherent_risk_score_id.score', store=True, readonly=True)
    inherent_label = fields.Char(
        related='inherent_risk_score_id.label', string='Inherent Risk', store=True, readonly=True,
    )
    inherent_bg_color = fields.Char(related='inherent_risk_score_id.bg_color', readonly=True)
    inherent_text_color = fields.Char(related='inherent_risk_score_id.text_color', readonly=True)

    residual_likelihood_id = fields.Many2one('risk.likelihood', string='Residual Likelihood')
    residual_consequence_id = fields.Many2one('risk.consequence', string='Residual Consequence')
    residual_risk_score_id = fields.Many2one(
        'risk.score', string='Residual Risk Matrix Cell', compute='_compute_risk_score_ids', store=True,
    )
    residual_severity_id = fields.Many2one(
        related='residual_risk_score_id.severity_id', string='Residual Severity', store=True, readonly=True,
    )
    residual_score = fields.Integer(related='residual_risk_score_id.score', store=True, readonly=True)
    residual_label = fields.Char(
        related='residual_risk_score_id.label', string='Residual Risk', store=True, readonly=True,
    )
    residual_bg_color = fields.Char(related='residual_risk_score_id.bg_color', readonly=True)
    residual_text_color = fields.Char(related='residual_risk_score_id.text_color', readonly=True)

    ai_available = fields.Boolean(compute='_compute_ai_available')

    @api.depends(
        'inherent_likelihood_id', 'inherent_consequence_id',
        'residual_likelihood_id', 'residual_consequence_id',
    )
    def _compute_risk_score_ids(self):
        Score = self.env['risk.score']
        for line in self:
            line.inherent_risk_score_id = line._find_risk_score(
                line.inherent_likelihood_id, line.inherent_consequence_id, Score,
            )
            line.residual_risk_score_id = line._find_risk_score(
                line.residual_likelihood_id, line.residual_consequence_id, Score,
            )

    def _compute_ai_available(self):
        installed = bool(self.env['ir.module.module'].sudo().search_count([
            ('name', '=', 'claude_ai_settings'), ('state', '=', 'installed'),
        ]))
        for line in self:
            line.ai_available = installed

    def action_generate_risk_ai(self):
        """Fill in every empty field of this risk by AI, leaving filled-in fields as they are."""
        self.ensure_one()
        if not (self.name or '').strip():
            raise UserError('Give the risk a name before filling it in by AI.')
        if not self._ai_risk_empty_fields():
            raise UserError('Every field of this risk is already filled in.')
        api_key = self.env['ir.config_parameter'].sudo().get_param('claude_ai_settings.api_key')
        if not api_key:
            raise UserError('Set a Claude AI API Key first (Settings > General Settings > Claude AI).')
        text = ai_request_text(api_key, self._ai_risk_prompt(), self._ai_risk_max_tokens, self._ai_risk_timeout)
        data = ai_parse_json(text)
        if not isinstance(data, dict):
            raise UserError(
                'The AI response could not be understood. Please try again.\n\n'
                'Start of the raw response:\n%s' % (text or '')[:500]
            )
        vals = self._ai_risk_vals(data)
        if vals:
            self.write(vals)
        return True

    def get_ai_empty_field_labels(self):
        """Labels of the fields "Fill Empty Fields by AI" will fill in, for its progress overlay."""
        self.ensure_one()
        return [self._fields[name].string for name in self._ai_risk_empty_fields()]

    def _ai_risk_empty_fields(self):
        """Names of the fields "Fill Empty Fields by AI" would fill in on this risk."""
        self.ensure_one()
        names = [
            'unwanted_event', 'description', 'risk_type_id', 'risk_subtype_id',
            'inherent_likelihood_id', 'inherent_consequence_id', 'control_ids', 'control_summary',
            'residual_likelihood_id', 'residual_consequence_id',
        ]
        if self._ai_actions_field:
            names.append(self._ai_actions_field)
        return [name for name in names if not self[name]]

    def _ai_risk_prompt(self):
        self.ensure_one()
        parent = self[self._ai_parent_field] if self._ai_parent_field else None
        summary = parent.summary_of_activity if parent and 'summary_of_activity' in parent._fields else ''
        types = self.env['risk.type'].search([]).mapped('name')
        subtypes = [
            '%s > %s' % (subtype.risk_type_id.name, subtype.name)
            for subtype in self.env['risk.subtype'].search([], order='risk_type_id, name')
        ]
        controls = self.env['risk.control'].search([]).mapped('name')
        likelihoods = self.env['risk.likelihood'].search([], order='sequence, value').mapped('name')
        consequences = self.env['risk.consequence'].search([], order='sequence, value').mapped('name')
        details = [
            ('Activity summary', summary),
            ('Risk', self.name),
            ('%s (unwanted_event)' % self._fields['unwanted_event'].string, self.unwanted_event),
            ('Description', self.description),
            ('Risk Type', self.risk_type_id.name),
            ('Risk Subtype', self.risk_subtype_id.name),
            ('Inherent Likelihood', self.inherent_likelihood_id.name),
            ('Inherent Consequence', self.inherent_consequence_id.name),
            ('Controls', ', '.join(self.control_ids.mapped('name'))),
            ('Controls Summary', self.control_summary),
            ('Residual Likelihood', self.residual_likelihood_id.name),
            ('Residual Consequence', self.residual_consequence_id.name),
        ]
        return (
            "You are a Work Health & Safety risk assessor for a youth Scouting organisation in "
            "Australia. Complete the risk below. Keep what is already filled in and make every "
            "suggestion consistent with it: the INHERENT risk is how likely and how severe it "
            "would be with NO controls in place, and the RESIDUAL risk is how likely and how "
            "severe it would be once all of the risk's controls (the existing ones, or the ones "
            "you suggest) are in place.\n\n"
            + ''.join('%s: %s\n' % (label, value) for label, value in details if value) + "\n"
            "Existing Risk Types - reuse one of these names if it fits, otherwise suggest a new "
            "short Risk Type name:\n" + ', '.join(types or ['(none yet)']) + "\n\n"
            "Existing Risk Subtypes, shown as 'Risk Type > Subtype' - reuse one that belongs to "
            "the risk_type if it fits, otherwise suggest a new short Subtype name:\n"
            + ', '.join(subtypes or ['(none yet)']) + "\n\n"
            "Existing Controls already in our library - reuse a name below if it fits, otherwise "
            "suggest a new short Control name:\n"
            + ', '.join(controls or ['(none yet)']) + "\n\n"
            "Likelihood bands (choose exactly one of these names for inherent_likelihood and "
            "residual_likelihood, lowest to highest): " + ', '.join(likelihoods or ['(none configured)']) + "\n\n"
            "Consequence bands (choose exactly one of these names for inherent_consequence and "
            "residual_consequence, lowest to highest): " + ', '.join(consequences or ['(none configured)']) + "\n\n"
            "Respond with ONLY a JSON object (no other text, no markdown code fences) with this "
            "exact shape:\n"
            '{"unwanted_event": "what could go wrong", '
            '"description": "1-2 sentence description of the risk", '
            '"risk_type": "Risk Type name", '
            '"risk_subtype": "Risk Subtype name, belonging to that Risk Type", '
            '"inherent_likelihood": "Likelihood band name", '
            '"inherent_consequence": "Consequence band name", '
            '"controls": ["Control name", "Control name"], '
            '"control_summary": "2-4 sentences on how the controls work together to manage this risk", '
            '"residual_likelihood": "Likelihood band name", '
            '"residual_consequence": "Consequence band name", '
            '"actions": [{"name": "short follow-up action to put the controls in place", '
            '"description": "1 sentence"}]}'
        )

    def _ai_risk_vals(self, data):
        """Values for this risk's empty fields from one AI answer. Filled-in fields, and
        anything the AI named that can't be matched (e.g. an unknown band), are left alone."""
        self.ensure_one()
        empty = set(self._ai_risk_empty_fields())

        def text(key):
            value = data.get(key)
            return value.strip() if isinstance(value, str) else ''

        vals = {}
        for field_name in ('unwanted_event', 'description', 'control_summary'):
            if field_name in empty and text(field_name):
                vals[field_name] = text(field_name)

        risk_type = self.risk_type_id
        if 'risk_type_id' in empty and text('risk_type'):
            risk_type = self._ai_find_or_create('risk.type', [('name', '=ilike', text('risk_type'))], {
                'name': text('risk_type'),
            })
            if risk_type:
                vals['risk_type_id'] = risk_type.id
        if 'risk_subtype_id' in empty and text('risk_subtype') and risk_type:
            subtype = self._ai_find_or_create('risk.subtype', [
                ('risk_type_id', '=', risk_type.id), ('name', '=ilike', text('risk_subtype')),
            ], {'name': text('risk_subtype'), 'risk_type_id': risk_type.id})
            if subtype:
                vals['risk_subtype_id'] = subtype.id

        for key, model in (
            ('inherent_likelihood', 'risk.likelihood'), ('inherent_consequence', 'risk.consequence'),
            ('residual_likelihood', 'risk.likelihood'), ('residual_consequence', 'risk.consequence'),
        ):
            if key + '_id' in empty and text(key):
                band = self.env[model].search([('name', '=ilike', text(key))], limit=1)
                if band:
                    vals[key + '_id'] = band.id

        names = [name.strip() for name in data.get('controls') or [] if isinstance(name, str) and name.strip()]
        if 'control_ids' in empty and names:
            controls = self.env['risk.control'].browse()
            for name in names:
                controls |= self._ai_find_or_create('risk.control', [('name', '=ilike', name)], {'name': name})
            if controls:
                vals['control_ids'] = [(6, 0, controls.ids)]

        actions = [
            action for action in data.get('actions') or []
            if isinstance(action, dict) and isinstance(action.get('name'), str) and action['name'].strip()
        ]
        if self._ai_actions_field in empty and actions:
            vals.update(self._ai_risk_action_vals(actions))
        return vals

    def _ai_risk_action_vals(self, actions):
        """Values adding the AI-suggested actions; set by each concrete model."""
        return {}

    def _ai_find_or_create(self, model, domain, vals):
        """The record matching an AI suggestion, created if new and the user may create one
        (otherwise an empty recordset, so the suggestion is skipped)."""
        Model = self.env[model]
        record = Model.search(domain, limit=1)
        if not record and Model.has_access('create'):
            record = Model.create(vals)
        return record

    @api.onchange('risk_type_id')
    def _onchange_risk_type_id(self):
        if self.risk_subtype_id and self.risk_subtype_id.risk_type_id != self.risk_type_id:
            self.risk_subtype_id = False

    def _find_risk_score(self, likelihood, consequence, Score=None):
        Score = Score or self.env['risk.score']
        if likelihood and consequence:
            return Score.search([
                ('likelihood_id', '=', likelihood.id),
                ('consequence_id', '=', consequence.id),
            ], limit=1)
        return Score.browse()

    def get_formview_id(self, access_uid=None):
        if self._form_view_xmlid:
            view = self.env.ref(self._form_view_xmlid, raise_if_not_found=False)
            if view:
                return view.id
        return super().get_formview_id(access_uid=access_uid)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.control_ids._ai_fill_missing_descriptions()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if 'control_ids' in vals:
            self.control_ids._ai_fill_missing_descriptions()
        return result

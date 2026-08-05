# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ApiModelEndpoint(models.Model):
    _name = "api.model.endpoint"
    _description = "API Model Endpoint"
    _order = "name"

    _constraint_model_unique = models.Constraint(
        "unique(model_id)", "Only one endpoint per model is allowed."
    )

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    require_api_key = fields.Boolean(
        string="Require API Key or Session",
        default=True,
        help="If enabled, request must include a valid API key or an authenticated session cookie.",
    )
    rate_limit_enabled = fields.Boolean(default=False)
    rate_limit_per_minute = fields.Integer(default=60)

    model_id = fields.Many2one("ir.model", required=True, ondelete="cascade")
    field_ids = fields.Many2many(
        "ir.model.fields",
        "api_model_endpoint_field_rel",
        "endpoint_id",
        "field_id",
        string="Fields",
        domain="[('model_id','=',model_id)]",
    )
    select_all_fields = fields.Boolean(string="Select All Fields", default=False)
    relation_ids = fields.One2many(
        "api.model.endpoint.relation", "endpoint_id", string="Related Models"
    )
    domain = fields.Char(help="Odoo domain for filtering records, e.g. [('state','=','sale')]")
    endpoint_url = fields.Char(compute="_compute_endpoint_url", readonly=True)

    @api.onchange("model_id")
    def _onchange_model_id(self):
        if not self.model_id:
            self.field_ids = [(5, 0, 0)]
            self.select_all_fields = False
            self.relation_ids = [(5, 0, 0)]
            return

        self.select_all_fields = True
        fields_ids = self.env["ir.model.fields"].search(
            [("model_id", "=", self.model_id.id)]
        ).ids
        self.field_ids = [(6, 0, fields_ids)]

        relation_fields = self.env["ir.model.fields"].search(
            [
                ("model_id", "=", self.model_id.id),
                ("ttype", "in", ("one2many", "many2many", "many2one")),
            ]
        )
        relation_commands = [(5, 0, 0)]
        IrModel = self.env["ir.model"]
        for rel_field in relation_fields:
            related_model = IrModel.search(
                [("model", "=", rel_field.relation)], limit=1
            )
            if not related_model:
                continue
            related_field_ids = self.env["ir.model.fields"].search(
                [("model_id", "=", related_model.id)]
            ).ids
            relation_commands.append(
                (
                    0,
                    0,
                    {
                        "relation_field_id": rel_field.id,
                        "related_model_id": related_model.id,
                        "select_all_fields": True,
                        "field_ids": [(6, 0, related_field_ids)],
                    },
                )
            )
        self.relation_ids = relation_commands

    @api.onchange("select_all_fields", "model_id")
    def _onchange_select_all_fields(self):
        if not self.model_id:
            self.field_ids = [(5, 0, 0)]
            return
        if self.select_all_fields:
            fields_ids = self.env["ir.model.fields"].search(
                [("model_id", "=", self.model_id.id)]
            ).ids
            self.field_ids = [(6, 0, fields_ids)]
        else:
            self.field_ids = [(5, 0, 0)]

    @api.depends("model_id")
    def _compute_endpoint_url(self):
        for record in self:
            if record.model_id and record.model_id.model:
                record.endpoint_url = f"/api/model/{record.model_id.model}"
            else:
                record.endpoint_url = False


class ApiCustomEndpoint(models.Model):
    _name = "api.custom.endpoint"
    _description = "API Custom Endpoint"
    _order = "name"

    _constraint_route_unique = models.Constraint(
        "unique(route)", "Route must be unique."
    )

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    require_api_key = fields.Boolean(
        string="Require API Key or Session",
        default=True,
        help="If enabled, request must include a valid API key or an authenticated session cookie.",
    )
    rate_limit_enabled = fields.Boolean(default=False)
    rate_limit_per_minute = fields.Integer(default=60)

    route = fields.Char(required=True, help="URL slug used in /api/custom/<route>")
    full_route = fields.Char(compute="_compute_full_route", store=True, readonly=True)
    response_type = fields.Selection(
        [
            ("json", "JSON"),
            ("text", "Text"),
        ],
        default="json",
        required=True,
    )
    response_body = fields.Text(required=True)

    @api.depends("route")
    def _compute_full_route(self):
        for record in self:
            if record.route:
                record.full_route = f"/api/custom/{record.route}"
            else:
                record.full_route = False

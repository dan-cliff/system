# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ApiModelEndpointRelation(models.Model):
    _name = "api.model.endpoint.relation"
    _description = "API Model Endpoint Relation"
    _order = "relation_field_id"

    endpoint_id = fields.Many2one(
        "api.model.endpoint", required=True, ondelete="cascade"
    )
    relation_field_id = fields.Many2one(
        "ir.model.fields",
        required=True,
        ondelete="cascade",
        domain="[('ttype','in',('one2many','many2many','many2one'))]",
    )
    related_model_id = fields.Many2one(
        "ir.model",
        compute="_compute_related_model_id",
        store=True,
        readonly=True,
        ondelete="cascade",
    )
    field_ids = fields.Many2many(
        "ir.model.fields",
        "api_model_endpoint_relation_field_rel",
        "relation_id",
        "field_id",
        string="Related Fields",
        domain="[('model_id','=',related_model_id)]",
    )
    select_all_fields = fields.Boolean(string="Select All Fields", default=True)

    @api.depends("relation_field_id")
    def _compute_related_model_id(self):
        for rec in self:
            if not rec.relation_field_id:
                rec.related_model_id = False
                continue
            model = rec.relation_field_id.relation
            rec.related_model_id = self.env["ir.model"].search(
                [("model", "=", model)], limit=1
            )

    @api.onchange("relation_field_id")
    def _onchange_relation_field_id(self):
        if not self.relation_field_id:
            self.field_ids = [(5, 0, 0)]
            self.select_all_fields = False
            return
        if self.select_all_fields:
            self._apply_select_all()

    @api.onchange("select_all_fields", "related_model_id")
    def _onchange_select_all_fields(self):
        if not self.related_model_id:
            self.field_ids = [(5, 0, 0)]
            return
        if self.select_all_fields:
            self._apply_select_all()
        else:
            self.field_ids = [(5, 0, 0)]

    def _apply_select_all(self):
        fields_ids = self.env["ir.model.fields"].search(
            [("model_id", "=", self.related_model_id.id)]
        ).ids
        self.field_ids = [(6, 0, fields_ids)]

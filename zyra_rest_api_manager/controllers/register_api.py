# -*- coding: utf-8 -*-

import json
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class ZyraRegisterApiController(http.Controller):
    def _json_response(self, payload, status=200, headers=None):
        return Response(
            json.dumps(payload, default=str),
            status=status,
            content_type="application/json",
            headers=headers,
        )

    def _parse_json_body(self):
        try:
            raw = request.httprequest.data or b""
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    @http.route(
        ["/api/register"],
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
    )
    def register(self, **kwargs):
        if request.httprequest.method != "POST":
            return self._json_response(
                {"error": "Method not allowed. Use POST for /api/register."},
                status=405,
                headers={"Allow": "POST"},
            )
        try:
            endpoint = (
                request.env["api.auth.endpoint"]
                .sudo()
                .search([("route", "=", "register")], limit=1)
            )
            if endpoint and not endpoint.active:
                return self._json_response({"error": "Endpoint disabled"}, status=403)

            payload = self._parse_json_body()
            if payload is None:
                return self._json_response({"error": "Invalid JSON"}, status=400)

            name = (payload.get("name") or "").strip()
            email = (payload.get("email") or "").strip().lower()
            password = payload.get("password")
            phone = (payload.get("phone") or "").strip()

            if not name or not email or not password:
                return self._json_response(
                    {"error": "Missing required fields: name, email, password"}, status=400
                )

            Users = request.env["res.users"].sudo()
            if Users.search([("login", "=", email)], limit=1):
                return self._json_response({"error": "User already exists"}, status=409)

            Partners = request.env["res.partner"].sudo()
            if Partners.search([("email", "=", email)], limit=1):
                return self._json_response({"error": "Email already exists"}, status=409)

            portal_group = request.env.ref("base.group_portal")
            user_vals = {
                "name": name,
                "login": email,
                "email": email,
                "password": password,
                "company_id": request.env.company.id,
                "company_ids": [(6, 0, [request.env.company.id])],
            }
            if "group_ids" in Users._fields:
                user_vals["group_ids"] = [(6, 0, [portal_group.id])]
            elif "groups_id" in Users._fields:
                user_vals["groups_id"] = [(6, 0, [portal_group.id])]
            if phone:
                user_vals["phone"] = phone

            user = Users.with_context(no_reset_password=True).create(user_vals)

            return self._json_response(
                {
                    "uid": user.id,
                    "partner_id": user.partner_id.id if user.partner_id else False,
                    "login": user.login,
                },
                status=201,
            )
        except Exception as err:
            _logger.exception("Unhandled error in /api/register")
            return self._json_response(
                {"error": "Internal server error", "route": "/api/register", "details": str(err)},
                status=500,
            )

# -*- coding: utf-8 -*-

import json
import inspect
from datetime import timedelta

from odoo import http, fields
from odoo.exceptions import AccessDenied
from odoo.http import request, Response
from odoo.service import db as service_db


class ZyraAuthApiController(http.Controller):
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

    def _resolve_db(self, payload_db):
        if payload_db:
            return payload_db
        if request.session.db:
            return request.session.db
        if getattr(request.env, "cr", None) and request.env.cr.dbname:
            return request.env.cr.dbname
        try:
            dbs = service_db.list_dbs(force=True)
        except Exception:
            dbs = []
        if len(dbs) == 1:
            return dbs[0]
        return None

    def _utc_now(self):
        now = fields.Datetime.now()
        if isinstance(now, str):
            now = fields.Datetime.from_string(now)
        return now

    def _cooldown_key(self, endpoint, identifier):
        ip = request.httprequest.remote_addr or "unknown"
        ident = (identifier or "").strip().lower()
        return f"{endpoint}|{ip}|{ident}"

    def _get_cooldown_log(self, endpoint, identifier):
        key = self._cooldown_key(endpoint, identifier)
        return (
            request.env["api.auth.cooldown.log"]
            .sudo()
            .search([("cooldown_key", "=", key)], limit=1)
        )

    def _check_cooldown(self, endpoint, identifier):
        log = self._get_cooldown_log(endpoint, identifier)
        if not log or not log.blocked_until:
            return None
        now = self._utc_now()
        blocked_until = log.blocked_until
        if isinstance(blocked_until, str):
            blocked_until = fields.Datetime.from_string(blocked_until)
        if now >= blocked_until:
            log.write(
                {
                    "failed_count": 0,
                    "window_start": False,
                    "blocked_until": False,
                }
            )
            return None
        retry_after = max(1, int((blocked_until - now).total_seconds()))
        return retry_after

    def _record_failed_attempt(
        self, endpoint, identifier, max_attempts, window_minutes, cooldown_minutes
    ):
        now = self._utc_now()
        key = self._cooldown_key(endpoint, identifier)
        Log = request.env["api.auth.cooldown.log"].sudo()
        log = Log.search([("cooldown_key", "=", key)], limit=1)
        if not log:
            Log.create(
                {
                    "cooldown_key": key,
                    "endpoint": endpoint,
                    "identifier": (identifier or "").strip().lower(),
                    "ip_address": request.httprequest.remote_addr or False,
                    "failed_count": 1,
                    "window_start": now,
                }
            )
            return None

        window_start = log.window_start
        if isinstance(window_start, str):
            window_start = fields.Datetime.from_string(window_start)

        if not window_start or (now - window_start) > timedelta(minutes=window_minutes):
            log.write(
                {
                    "failed_count": 1,
                    "window_start": now,
                    "blocked_until": False,
                }
            )
            return None

        failed_count = int(log.failed_count or 0) + 1
        values = {"failed_count": failed_count}
        if failed_count >= max_attempts:
            blocked_until = now + timedelta(minutes=cooldown_minutes)
            values["blocked_until"] = blocked_until
            retry_after = max(1, int((blocked_until - now).total_seconds()))
        else:
            retry_after = None
        log.write(values)
        return retry_after

    def _clear_failed_attempts(self, endpoint, identifier):
        log = self._get_cooldown_log(endpoint, identifier)
        if log:
            log.write({"failed_count": 0, "window_start": False, "blocked_until": False})

    def _get_endpoint_cooldown_policy(self, endpoint, default_max=5, default_window=15, default_cooldown=15):
        if not endpoint:
            return default_max, default_window, default_cooldown
        try:
            max_attempts = int(endpoint.max_failed_attempts or default_max)
        except Exception:
            max_attempts = default_max
        try:
            window_minutes = int(endpoint.failure_window_minutes or default_window)
        except Exception:
            window_minutes = default_window
        try:
            cooldown_minutes = int(endpoint.cooldown_minutes or default_cooldown)
        except Exception:
            cooldown_minutes = default_cooldown
        return max(1, max_attempts), max(1, window_minutes), max(1, cooldown_minutes)

    def _user_groups(self, user):
        if "group_ids" in user._fields:
            return user.group_ids.sudo()
        if "groups_id" in user._fields:
            return user.groups_id.sudo()
        return request.env["res.groups"].sudo().browse([])

    def _get_user_groups_payload(self, user):
        groups = self._user_groups(user)
        xmlids = groups.get_external_id()
        def _category_name(group):
            if "category_id" in group._fields and group.category_id:
                return group.category_id.name
            if "category" in group._fields:
                category = group.category
                if hasattr(category, "name"):
                    return category.name
                return category or False
            return False
        return [
            {
                "id": group.id,
                "name": group.name,
                "category": _category_name(group),
                "xml_id": xmlids.get(group.id),
            }
            for group in groups
        ]

    def _get_user_model_access_payload(self, user):
        groups = self._user_groups(user)
        access_records = (
            request.env["ir.model.access"]
            .sudo()
            .search(["|", ("group_id", "=", False), ("group_id", "in", groups.ids)])
        )
        return [
            {
                "id": access.id,
                "name": access.name,
                "model": access.model_id.model if access.model_id else False,
                "group": access.group_id.name if access.group_id else False,
                "perm_read": bool(access.perm_read),
                "perm_write": bool(access.perm_write),
                "perm_create": bool(access.perm_create),
                "perm_unlink": bool(access.perm_unlink),
            }
            for access in access_records
        ]

    def _get_user_record_rules_payload(self, user):
        groups = self._user_groups(user)
        rules = (
            request.env["ir.rule"]
            .sudo()
            .search(
                [
                    ("active", "=", True),
                    ("model_id", "!=", False),
                    "|",
                    ("groups", "=", False),
                    ("groups", "in", groups.ids),
                ]
            )
        )
        return [
            {
                "id": rule.id,
                "name": rule.name,
                "model": rule.model_id.model if rule.model_id else False,
                "domain_force": rule.domain_force or "[]",
                "groups": rule.groups.mapped("name"),
                "perm_read": bool(rule.perm_read),
                "perm_write": bool(rule.perm_write),
                "perm_create": bool(rule.perm_create),
                "perm_unlink": bool(rule.perm_unlink),
            }
            for rule in rules
        ]

    @http.route(
        ["/api/login"],
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
    )
    def login(self, **kwargs):
        if request.httprequest.method != "POST":
            return self._json_response(
                {"error": "Method not allowed. Use POST for /api/login."},
                status=405,
                headers={"Allow": "POST"},
            )
        endpoint = (
            request.env["api.auth.endpoint"]
            .sudo()
            .search([("route", "=", "login")], limit=1)
        )
        if endpoint and not endpoint.active:
            return self._json_response({"error": "Endpoint disabled"}, status=403)
        max_attempts, window_minutes, cooldown_minutes = self._get_endpoint_cooldown_policy(endpoint)

        payload = self._parse_json_body()
        if payload is None:
            return self._json_response({"error": "Invalid JSON"}, status=400)

        login = payload.get("login")
        password = payload.get("password")
        db = self._resolve_db(payload.get("db"))
        login_key = (login or "").strip().lower()

        retry_after = self._check_cooldown("login", login_key)
        if retry_after:
            return self._json_response(
                {"error": "Too many failed attempts. Try again later."},
                status=429,
                headers={"Retry-After": str(retry_after)},
            )

        if not login or not password:
            return self._json_response(
                {"error": "Missing required fields: login, password"}, status=400
            )
        if not db:
            return self._json_response(
                {"error": "Database not specified and multiple databases exist"}, status=400
            )

        try:
            credential = {"type": "password", "login": login, "password": password}
            sig = inspect.signature(request.session.authenticate)
            params = list(sig.parameters.keys())

            if params == ["env", "credential"]:
                auth_info = request.session.authenticate(request.env, credential)
            elif params == ["db", "credential"]:
                auth_info = request.session.authenticate(db, credential)
            elif params == ["db", "login", "password"]:
                auth_info = request.session.authenticate(db, login, password)
            else:
                raise TypeError(
                    "Unsupported authenticate signature: %s" % ", ".join(params)
                )

            if isinstance(auth_info, dict):
                uid = auth_info.get("uid")
            else:
                uid = auth_info
            if not uid:
                self._record_failed_attempt(
                    "login",
                    login_key,
                    max_attempts,
                    window_minutes,
                    cooldown_minutes,
                )
                return self._json_response({"error": "Invalid credentials"}, status=401)
            user = request.env["res.users"].sudo().browse(uid)
        except AccessDenied:
            self._record_failed_attempt(
                "login",
                login_key,
                max_attempts,
                window_minutes,
                cooldown_minutes,
            )
            return self._json_response({"error": "Invalid credentials"}, status=401)

        self._clear_failed_attempts("login", login_key)
        return self._json_response(
            {
                "uid": uid,
                "db": db,
                "session_id": request.session.sid,
                "company_id": user.company_id.id if user.company_id else False,
                "partner_id": user.partner_id.id if user.partner_id else False,
            }
        )

    @http.route(
        ["/api/password/reset"],
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
    )
    def reset_password(self, **kwargs):
        if request.httprequest.method != "POST":
            return self._json_response(
                {"error": "Method not allowed. Use POST for /api/password/reset."},
                status=405,
                headers={"Allow": "POST"},
            )
        endpoint = (
            request.env["api.auth.endpoint"]
            .sudo()
            .search([("route", "=", "reset_password")], limit=1)
        )
        if endpoint and not endpoint.active:
            return self._json_response({"error": "Endpoint disabled"}, status=403)
        max_attempts, window_minutes, cooldown_minutes = self._get_endpoint_cooldown_policy(endpoint)

        payload = self._parse_json_body()
        if payload is None:
            return self._json_response({"error": "Invalid JSON"}, status=400)

        email = (payload.get("email") or "").strip().lower()
        if not email:
            return self._json_response({"error": "Missing required field: email"}, status=400)

        retry_after = self._check_cooldown("reset_password", email)
        if retry_after:
            return self._json_response(
                {"error": "Too many failed attempts. Try again later."},
                status=429,
                headers={"Retry-After": str(retry_after)},
            )

        # Do not disclose whether the user exists; always return a generic response.
        users = request.env["res.users"].sudo().search(
            ["|", ("login", "=", email), ("email", "=", email)]
        )
        retry_after = self._record_failed_attempt(
            "reset_password",
            email,
            max_attempts,
            window_minutes,
            cooldown_minutes,
        )
        if retry_after:
            return self._json_response(
                {"error": "Too many failed attempts. Try again later."},
                status=429,
                headers={"Retry-After": str(retry_after)},
            )

        if users:
            try:
                users.action_reset_password()
            except Exception:
                pass

        return self._json_response(
            {"message": "If the account exists, a password reset email has been sent."}
        )

    @http.route(
        ["/api/user/details"],
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
    )
    def user_details(self, **kwargs):
        endpoint = (
            request.env["api.auth.endpoint"]
            .sudo()
            .search([("route", "=", "user_details")], limit=1)
        )
        if endpoint and not endpoint.active:
            return self._json_response({"error": "Endpoint disabled"}, status=403)

        uid = request.session.uid
        if not uid:
            return self._json_response(
                {"error": "Unauthorized. Login first and send session cookie."},
                status=401,
            )

        user = request.env["res.users"].sudo().browse(uid)
        if not user.exists():
            return self._json_response({"error": "User not found"}, status=404)

        payload = {
            "id": user.id,
            "name": user.name,
            "login": user.login,
            "email": user.email,
            "partner_id": user.partner_id.id if user.partner_id else False,
            "company_id": user.company_id.id if user.company_id else False,
            "company_ids": user.company_ids.ids,
            "active": bool(user.active),
            "lang": user.lang,
            "tz": user.tz,
            "groups": self._get_user_groups_payload(user),
            "model_access": self._get_user_model_access_payload(user),
            "record_rules": self._get_user_record_rules_payload(user),
        }
        return self._json_response(payload)

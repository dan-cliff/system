# -*- coding: utf-8 -*-

import json
import logging

from werkzeug.urls import url_encode

from odoo import http, fields
from odoo import SUPERUSER_ID
from odoo.exceptions import AccessError
from odoo.http import request, Response
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class ZyraApiController(http.Controller):
    def _get_api_key(self):
        return (
            request.httprequest.headers.get("X-API-Key")
            or request.httprequest.headers.get("Authorization", "").replace("Bearer ", "")
            or request.params.get("api_key")
        )

    def _is_api_key_valid(self):
        key = self._get_api_key()
        if not key:
            return False
        return bool(
            request.env["api.app.key"].sudo().search(
                [("key", "=", key), ("active", "=", True)], limit=1
            )
        )

    def _is_session_authenticated(self):
        return bool(request.session.uid)

    def _require_key_or_unauthorized(self):
        if self._is_api_key_valid() or self._is_session_authenticated():
            return None
        payload = json.dumps({"error": "Unauthorized. Provide API key or authenticated session."})
        return Response(payload, status=401, content_type="application/json")

    def _json_response(self, payload, status=200, headers=None):
        return Response(
            json.dumps(payload, default=str),
            status=status,
            content_type="application/json",
            headers=headers,
        )

    def _parse_int(self, value, default):
        try:
            return int(value)
        except Exception:
            return default

    def _rate_limit_identifier(self):
        key = self._get_api_key()
        if key:
            return f"key:{key}"
        if request.session.uid:
            return f"user:{request.session.uid}"
        return f"ip:{request.httprequest.remote_addr}"

    def _check_rate_limit(self, endpoint):
        if not endpoint.rate_limit_enabled:
            return None
        limit = int(endpoint.rate_limit_per_minute or 0)
        if limit <= 0:
            return None

        identifier = self._rate_limit_identifier()
        now = fields.Datetime.now()
        if isinstance(now, str):
            now = fields.Datetime.from_string(now)
        window_start = now.replace(second=0, microsecond=0)

        RateLog = request.env["api.rate.limit.log"].sudo()
        log = RateLog.search(
            [
                ("endpoint_model", "=", endpoint._name),
                ("endpoint_record_id", "=", endpoint.id),
                ("identifier", "=", identifier),
                ("window_start", "=", window_start),
            ],
            limit=1,
        )
        if not log:
            RateLog.create(
                {
                    "endpoint_model": endpoint._name,
                    "endpoint_record_id": endpoint.id,
                    "identifier": identifier,
                    "window_start": window_start,
                    "count": 1,
                }
            )
            return None

        if log.count >= limit:
            reset_seconds = 60 - now.second
            headers = {"Retry-After": str(reset_seconds)}
            return self._json_response({"error": "Rate limit exceeded"}, status=429, headers=headers)

        log.count += 1
        return None

    def _parse_json_body(self):
        try:
            raw = request.httprequest.data or b""
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def _filter_payload(self, payload, allowed_fields):
        if not isinstance(payload, dict):
            return {}
        return {k: v for k, v in payload.items() if k in allowed_fields}

    def _build_next_link(self, base_url, params, offset, limit, total):
        if offset + limit >= total:
            return None
        # Exclude auth and route params; path already contains the model and record context.
        excluded = {"api_key", "model_name", "record_id"}
        cleaned = {k: v for k, v in params.items() if k not in excluded}
        cleaned["limit"] = limit
        cleaned["offset"] = offset + limit
        qs = url_encode(cleaned)
        return f"{base_url}?{qs}" if qs else base_url

    def _parse_domain_param(self, raw_domain):
        if not raw_domain:
            return []
        try:
            domain = safe_eval(raw_domain)
        except Exception:
            return None
        if isinstance(domain, (list, tuple)):
            return list(domain)
        return None

    def _add_related_data(
        self,
        record,
        data,
        relations,
        skipped_fields=None,
        ignore_access_errors=False,
        binary_as_size=False,
    ):
        for rel in relations:
            field = rel.relation_field_id.name
            if field not in record._fields:
                continue
            rel_fields = rel.field_ids.mapped("name") or ["id"]
            field_type = record._fields[field].type
            try:
                value = record[field]
                if binary_as_size:
                    value = value.with_context(bin_size=True)
                if field_type == "many2one":
                    data[field] = value.read(rel_fields)[0] if value else False
                else:
                    data[field] = value.read(rel_fields)
            except AccessError as err:
                if not ignore_access_errors:
                    raise
                if skipped_fields is not None:
                    skipped_fields.append({"field": field, "error": str(err), "source": "relation"})
                data[field] = False if field_type == "many2one" else []

    def _safe_read_records(
        self, records, fields_list, ignore_access_errors=False, binary_as_size=False
    ):
        if binary_as_size:
            records = records.with_context(bin_size=True)
        try:
            return records.read(fields_list), []
        except AccessError:
            if not ignore_access_errors:
                raise
            skipped = []
            rows_by_id = {rec.id: {"id": rec.id} for rec in records}
            for field_name in fields_list:
                try:
                    field_rows = records.read([field_name])
                    for row in field_rows:
                        row_id = row.get("id")
                        if row_id not in rows_by_id:
                            rows_by_id[row_id] = {"id": row_id}
                        rows_by_id[row_id][field_name] = row.get(field_name)
                except AccessError as err:
                    skipped.append({"field": field_name, "error": str(err)})
            data = [rows_by_id[rec.id] for rec in records]
            return data, skipped

    @http.route(
        [
            "/api/model/<string:model_name>",
            "/api/model/<string:model_name>/<int:record_id>",
        ],
        type="http",
        auth="public",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        csrf=False,
    )
    def model_endpoint(self, model_name, record_id=None, **kwargs):
        if model_name not in request.env:
            return self._json_response({"error": "Model not found"}, status=404)

        try:
            endpoint = (
                request.env["api.model.endpoint"]
                .sudo()
                .search([("model_id.model", "=", model_name), ("active", "=", True)], limit=1)
            )
            if not endpoint:
                return self._json_response({"error": "Endpoint not found"}, status=404)

            if endpoint.require_api_key:
                unauthorized = self._require_key_or_unauthorized()
                if unauthorized:
                    return unauthorized

            rate_limited = self._check_rate_limit(endpoint)
            if rate_limited:
                return rate_limited

            use_superuser = not endpoint.require_api_key
            model = request.env[model_name].with_user(SUPERUSER_ID) if use_superuser else request.env[model_name]
            fields_list = endpoint.field_ids.mapped("name") or ["id"]

            method = request.httprequest.method

            if method in ["POST", "PUT", "PATCH"]:
                payload = self._parse_json_body()
                if payload is None:
                    return self._json_response({"error": "Invalid JSON"}, status=400)
                values = self._filter_payload(payload, set(fields_list))

                if method == "POST":
                    if record_id:
                        return self._json_response({"error": "POST does not accept record id"}, status=400)
                    record = model.create(values)
                    data, skipped_fields = self._safe_read_records(
                        record, fields_list, ignore_access_errors=use_superuser
                    )
                    return self._json_response(
                        {"model": model_name, "data": data[0], "skipped_fields": skipped_fields},
                        status=201,
                    )

                if not record_id:
                    return self._json_response({"error": "Record id is required"}, status=400)
                record = model.browse(record_id)
                if not record.exists():
                    return self._json_response({"error": "Record not found"}, status=404)
                record.write(values)
                data, skipped_fields = self._safe_read_records(
                    record, fields_list, ignore_access_errors=use_superuser
                )
                return self._json_response(
                    {"model": model_name, "data": data[0], "skipped_fields": skipped_fields}
                )

            if method == "DELETE":
                if not record_id:
                    return self._json_response({"error": "Record id is required"}, status=400)
                record = model.browse(record_id)
                if not record.exists():
                    return self._json_response({"error": "Record not found"}, status=404)
                record.unlink()
                return self._json_response({"model": model_name, "deleted": True})

            if record_id:
                record = model.browse(record_id)
                if not record.exists():
                    return self._json_response({"error": "Record not found"}, status=404)
                data, skipped_fields = self._safe_read_records(
                    record, fields_list, ignore_access_errors=use_superuser
                )
                result = data[0]
                if endpoint.relation_ids:
                    self._add_related_data(
                        record,
                        result,
                        endpoint.relation_ids,
                        skipped_fields,
                        ignore_access_errors=use_superuser,
                    )
                return self._json_response(
                    {"model": model_name, "data": result, "skipped_fields": skipped_fields}
                )

            domain = []
            if endpoint.domain:
                try:
                    domain = safe_eval(endpoint.domain)
                except Exception:
                    return self._json_response({"error": "Invalid endpoint domain"}, status=400)

            request_domain = self._parse_domain_param(request.params.get("domain"))
            if request_domain is None:
                return self._json_response({"error": "Invalid request domain"}, status=400)
            if request_domain:
                domain = domain + request_domain

            limit = self._parse_int(request.params.get("limit", 100), 100)
            offset = self._parse_int(request.params.get("offset", 0), 0)
            order = request.params.get("order")

            records = model.search(domain, limit=limit, offset=offset, order=order)
            data, skipped_fields = self._safe_read_records(
                records,
                fields_list,
                ignore_access_errors=use_superuser,
                binary_as_size=True,
            )
            if endpoint.relation_ids and records:
                for record, row in zip(records, data):
                    self._add_related_data(
                        record,
                        row,
                        endpoint.relation_ids,
                        skipped_fields,
                        ignore_access_errors=use_superuser,
                        binary_as_size=True,
                    )
            total = model.search_count(domain)
            next_link = self._build_next_link(
                request.httprequest.base_url, request.params, offset, limit, total
            )

            return self._json_response(
                {
                    "model": model_name,
                    "count": len(data),
                    "total": total,
                    "next": next_link,
                    "skipped_fields": skipped_fields,
                    "data": data,
                }
            )
        except AccessError as err:
            return self._json_response(
                {
                    "error": "Access denied",
                    "model": model_name,
                    "details": str(err),
                },
                status=403,
            )
        except Exception as err:
            _logger.exception("Unhandled error in model endpoint for %s", model_name)
            return self._json_response(
                {
                    "error": "Internal server error",
                    "model": model_name,
                    "details": str(err),
                },
                status=500,
            )

    @http.route(
        ["/api/custom/<string:route_key>"],
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def custom_endpoint(self, route_key, **kwargs):
        endpoint = (
            request.env["api.custom.endpoint"]
            .sudo()
            .search([("route", "=", route_key), ("active", "=", True)], limit=1)
        )
        if not endpoint:
            return self._json_response({"error": "Endpoint not found"}, status=404)

        if endpoint.require_api_key:
            unauthorized = self._require_key_or_unauthorized()
            if unauthorized:
                return unauthorized

        rate_limited = self._check_rate_limit(endpoint)
        if rate_limited:
            return rate_limited

        if endpoint.response_type == "text":
            return Response(endpoint.response_body or "", content_type="text/plain")

        try:
            payload = json.loads(endpoint.response_body or "{}")
        except Exception:
            return self._json_response({"error": "Invalid JSON response"}, status=500)
        return self._json_response(payload)

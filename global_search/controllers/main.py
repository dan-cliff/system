import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

# Targets that open a proper full-window navigation (not a dialog/inline popup)
_GOOD_TARGETS = frozenset({'current', 'main', False, ''})

# ── Per-model extra search fields ─────────────────────────────────────────────
# For each model listed here, search results are widened to also match on these
# related field paths (OR'd with the primary name field).
# This lets users find e.g. a sale order by customer name or by product name.
MODEL_EXTRA_FIELDS = {
    'sale.order': [
        'partner_id.name',                           # customer name
        'client_order_ref',                          # customer's own PO reference
        'order_line.product_id.name',                # product name in order lines
        'order_line.product_id.default_code',        # product internal reference / SKU
    ],
    'purchase.order': [
        'partner_id.name',                           # vendor / supplier name
        'order_line.product_id.name',                # product name in order lines
        'order_line.product_id.default_code',        # product internal reference / SKU
    ],
    'account.move': [
        'partner_id.name',                           # customer or vendor name
        'ref',                                       # vendor bill / payment reference
        'invoice_line_ids.product_id.name',          # product name in invoice lines
        'invoice_line_ids.product_id.default_code',  # product internal reference / SKU
    ],
}

# ── Models excluded from global search ────────────────────────────────────────
# Internal / technical models that produce noise or are too granular.
SKIP_MODELS = frozenset({
    # Odoo internals
    'ir.ui.view', 'ir.ui.menu', 'ir.ui.icon',
    'ir.rule', 'ir.model', 'ir.model.fields', 'ir.model.access', 'ir.model.data',
    'ir.translation', 'ir.config_parameter', 'ir.default', 'ir.cron',
    'ir.actions.act_window', 'ir.actions.report', 'ir.actions.server',
    'ir.actions.act_url', 'ir.actions.client', 'ir.attachment',
    'ir.filters', 'ir.exports', 'ir.exports.line',
    'decimal.precision', 'ir.module.module', 'ir.module.category',
    # Mail / messaging
    'mail.message', 'mail.notification', 'mail.followers',
    'mail.tracking.value', 'mail.compose.message', 'mail.alias',
    'mail.alias.domain', 'mail.blacklist', 'mail.template', 'mail.channel',
    'mail.channel.member', 'mail.link.preview',
    # Bus
    'bus.bus', 'bus.channel', 'bus.channel.member',
    # Auth / session
    'res.users.log', 'res.users.deletion',
    # Too-granular order lines / moves (prefer the parent)
    'sale.order.line', 'purchase.order.line', 'account.move.line',
    'stock.move', 'stock.move.line', 'stock.quant',
    'mrp.bom.line', 'mrp.workorder',
    # Digest / misc
    'digest.digest', 'digest.tip',
    'base.language.install', 'base.language.export', 'base.language.import',
    'base.setup.act_window',
    'web_editor.converter.test',
})


def _build_action_map(env):
    """
    Return a dict { model_name: action_id } choosing the *best* act_window
    action for each model.

    Selection criteria (higher score wins):
      +4  target is 'current' / 'main' / False / '' (not a dialog/inline popup)
      +3  view_mode contains 'form'
      +2  res_id is not set  (action is generic, not pinned to one record)

    This ensures that, e.g., product.template resolves to the main product
    catalog action rather than the POS quick-info dialog action.
    """
    actions = env['ir.actions.act_window'].sudo().search([])
    best = {}   # model → (score, action_id)

    for action in actions:
        model = action.res_model
        if not model:
            continue

        score = 0
        if action.target in _GOOD_TARGETS:
            score += 4
        if 'form' in (action.view_mode or ''):
            score += 3
        if not action.res_id:
            score += 2

        current = best.get(model)
        if current is None or score > current[0]:
            best[model] = (score, action.id)

    return {model: data[1] for model, data in best.items()}


def _build_search_domain(primary_field, query, extra_fields, date_clauses):
    """
    Build an Odoo domain that OR's the primary field with any extra fields,
    then AND's the result with date_clauses.

    Conceptually:
        (primary_field ilike query
         OR extra_field_1 ilike query
         OR ...
        ) AND date_clause_1 AND date_clause_2 ...

    Odoo uses prefix OR notation: N conditions need N-1 '|' operators.
    """
    or_conditions = [(primary_field, 'ilike', query)]
    for field in extra_fields:
        or_conditions.append((field, 'ilike', query))

    n = len(or_conditions)
    if n == 1:
        domain = list(or_conditions)
    else:
        # N-1 '|' operators followed by N condition tuples
        domain = ['|'] * (n - 1) + or_conditions

    return domain + list(date_clauses)


def _get_record_details(record, model_name):
    """
    Return a dict of model-specific display details to show as a sub-line
    beneath the record title in the search results.

    Returns None for models that have no special handling.

    Fields returned (all optional / may be empty string):
      partner   – customer or vendor name
      reference – customer PO ref, vendor bill ref, or source document
      date      – order date or invoice date (DD/MM/YYYY)
    """
    try:
        if model_name == 'sale.order':
            partner = record.partner_id
            date_val = record.date_order
            return {
                'partner':   partner.name if partner else '',
                'reference': record.client_order_ref or '',
                'date':      date_val.strftime('%d/%m/%Y') if date_val else '',
            }

        if model_name == 'purchase.order':
            partner = record.partner_id
            date_val = record.date_order
            return {
                'partner':   partner.name if partner else '',
                'reference': '',
                'date':      date_val.strftime('%d/%m/%Y') if date_val else '',
            }

        if model_name == 'account.move':
            partner = record.partner_id
            # invoice_date is the document date; fall back to accounting date
            date_val = record.invoice_date or record.date
            # invoice_origin is the source SO/PO; fall back to journal ref
            ref = record.invoice_origin or record.ref or ''
            return {
                'partner':   partner.name if partner else '',
                'reference': ref,
                'date':      date_val.strftime('%d/%m/%Y') if date_val else '',
            }

    except Exception:
        pass

    return None


class GlobalSearchController(http.Controller):

    @http.route('/global_search/get_models', type='json', auth='user')
    def get_models(self):
        """Return the list of searchable, user-facing models."""
        action_map = _build_action_map(request.env)

        # Fetch ir.model rows in one query
        ir_models = request.env['ir.model'].sudo().search([
            ('model', 'in', list(action_map.keys())),
            ('transient', '=', False),
        ])

        result = []
        for ir_model in ir_models:
            model_name = ir_model.model
            try:
                Model = request.env.get(model_name)
                if Model is None:
                    continue
                # Only include if there's a searchable name-like field
                if not any(f in Model._fields for f in ('name', 'x_name', 'subject', 'title', 'reference')):
                    continue
                result.append({
                    'model': model_name,
                    'label': ir_model.name,
                    'action_id': action_map[model_name],
                })
            except Exception:
                continue

        result.sort(key=lambda x: x['label'].lower())
        return result

    @http.route('/global_search/search', type='json', auth='user')
    def search(self, query='', model_filter=None, date_from=None, date_to=None):
        """
        Search across all user-facing models (or a single model when filtered).

        Returns:
            { results: [...], total: int }
        """
        query = (query or '').strip()
        if len(query) < 2:
            return {'results': [], 'total': 0}

        # ── Action map (for URL generation) ───────────────────────────────────
        action_map = _build_action_map(request.env)

        # ── Model display-name map ─────────────────────────────────────────────
        ir_models_map = {
            m.model: m.name
            for m in request.env['ir.model'].sudo().search([('transient', '=', False)])
        }

        # ── Determine which models to search ──────────────────────────────────
        if model_filter and model_filter not in SKIP_MODELS:
            models_to_search = [model_filter]
        else:
            models_to_search = [m for m in action_map if m not in SKIP_MODELS]

        # ── Name-field priority list ───────────────────────────────────────────
        NAME_FIELDS = ('name', 'x_name', 'subject', 'title', 'reference')

        # ── Build date clauses ─────────────────────────────────────────────────
        date_domain_extra = []
        if date_from:
            date_domain_extra.append(('create_date', '>=', date_from + ' 00:00:00'))
        if date_to:
            date_domain_extra.append(('create_date', '<=', date_to + ' 23:59:59'))

        per_model_limit = 10
        results = []

        for model_name in models_to_search:
            try:
                Model = request.env.get(model_name)
                if Model is None:
                    continue

                # Pick the first available name-like field
                search_field = next(
                    (f for f in NAME_FIELDS if f in Model._fields), None
                )
                if not search_field:
                    continue

                # Skip if primary field is not stored (can't search efficiently)
                field_def = Model._fields[search_field]
                if hasattr(field_def, 'store') and not field_def.store:
                    continue

                extra_fields = MODEL_EXTRA_FIELDS.get(model_name, [])
                domain = _build_search_domain(
                    search_field, query, extra_fields, date_domain_extra
                )

                records = Model.search(
                    domain,
                    limit=per_model_limit,
                    order='create_date desc',
                )

                for record in records:
                    try:
                        create_date = record.create_date
                        row = {
                            'id': record.id,
                            'title': record.display_name or getattr(record, search_field, '') or str(record.id),
                            'model': model_name,
                            'model_label': ir_models_map.get(model_name, model_name),
                            'create_date': create_date.strftime('%d/%m/%Y') if create_date else '',
                            'create_date_iso': create_date.isoformat() if create_date else '',
                            'action_id': action_map.get(model_name),
                        }
                        details = _get_record_details(record, model_name)
                        if details:
                            row['details'] = details
                        results.append(row)
                    except Exception:
                        continue

            except AccessError:
                continue  # user has no read access to this model
            except Exception as exc:
                _logger.debug('GlobalSearch: error searching %s: %s', model_name, exc)
                continue

        # Sort by creation date descending; ungrouped flat list
        results.sort(key=lambda r: r.get('create_date_iso', ''), reverse=True)

        return {
            'results': results[:200],
            'total': len(results),
        }

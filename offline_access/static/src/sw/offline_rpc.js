// @odoo-module ignore

/* Offline Access: answers the web client's data requests (web_search_read,
 * web_read, web_read_group, ...) from the records kept on the device, in the
 * same shape the server would. Inserted into the service worker's main part.
 *
 * Plain functions over plain data: no service worker or browser APIs, so the
 * logic can be tested on its own.
 *
 *   model   {model, meta: {spec, order, models}} as stored by offline_store.js
 *   records the model's records, as web_read returned them for meta.spec
 */

const OFFLINE_X2MANY = new Set(["one2many", "many2many"]);
const OFFLINE_NUMBERS = new Set(["integer", "float", "monetary"]);
const OFFLINE_MAX_OPENED_GROUPS = 10;

const offlineFields = (model, modelName = model.model) =>
    model.meta?.models?.[modelName]?.fields || {};

// ── Domains ─────────────────────────────────────────────────────────────────

function offlineLike(value, pattern, caseInsensitive, exact) {
    if (value === false || value === null || value === undefined) {
        return false;
    }
    let text = String(value);
    let search = String(pattern);
    if (caseInsensitive) {
        text = text.toLowerCase();
        search = search.toLowerCase();
    }
    if (!exact) {
        return text.includes(search.replace(/%/g, ""));
    }
    const regex = search.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/%/g, ".*").replace(/_/g, ".");
    return new RegExp(`^${regex}$`, "s").test(text);
}

const offlineIsEmpty = (value) =>
    value === false || value === null || value === undefined || (Array.isArray(value) && !value.length);

/** A many2one or x2many element as {id, display_name}, or an id. */
const offlineId = (value) => (value && typeof value === "object" ? value.id : value);
const offlineName = (value) => (value && typeof value === "object" ? value.display_name : value);

function offlineCompare(value, operator, target) {
    const lowerOp = String(operator).toLowerCase();
    switch (lowerOp) {
        case "=":
        case "==":
            if (target === false || target === null) {
                return offlineIsEmpty(value);
            }
            if (value && typeof value === "object") {
                return typeof target === "string" ? value.display_name === target : value.id === target;
            }
            return value === target;
        case "!=":
        case "<>":
            return !offlineCompare(value, "=", target);
        case "in":
        case "child_of":
        case "parent_of": {
            const targets = Array.isArray(target) ? target : [target];
            return targets.some((t) => offlineCompare(value, "=", t));
        }
        case "not in":
            return !offlineCompare(value, "in", target);
        case "<":
        case ">":
        case "<=":
        case ">=": {
            const left = offlineId(value);
            if (left === false || left === null || left === undefined || target === false || target === null) {
                return false;
            }
            return { "<": left < target, ">": left > target, "<=": left <= target, ">=": left >= target }[lowerOp];
        }
        case "like":
        case "ilike":
        case "=like":
        case "=ilike":
            if (target === false || target === null || target === "") {
                return lowerOp.startsWith("=") ? offlineIsEmpty(value) : true;
            }
            return offlineLike(offlineName(value), target, lowerOp.includes("ilike"), lowerOp.startsWith("="));
        case "not like":
        case "not ilike":
            return !offlineCompare(value, operator.replace("not ", ""), target);
        default:
            return true; // not something we can check offline: don't hide the record
    }
}

function offlineCompileDomain(domain, model, modelName) {
    const fields = offlineFields(model, modelName);
    const items = Array.isArray(domain) ? domain : [];
    let index = 0;

    function leaf(condition) {
        if (!Array.isArray(condition) || condition.length !== 3) {
            return () => true;
        }
        const [path, operator, target] = condition;
        if (typeof path !== "string") {
            return () => offlineCompare(path, operator, target); // (1, '=', 1) / (0, '=', 1)
        }
        const [name, ...rest] = path.split(".");
        const field = fields[name] || {};
        const op = String(operator).toLowerCase();
        return (record) => {
            if (name === "id") {
                return offlineCompare(record.id, operator, target);
            }
            if (!(name in record)) {
                return true; // not kept offline: don't hide the record
            }
            const value = record[name];
            const elements = Array.isArray(value) ? value : [];
            const isX2many = OFFLINE_X2MANY.has(field.type) || Array.isArray(value);
            if (rest.length) {
                // Following a relation: only its id and name are kept offline.
                const sub = rest.join(".");
                if (!["id", "display_name", "name"].includes(sub)) {
                    return true;
                }
                const pick = (v) => (sub === "id" ? offlineId(v) : offlineName(v));
                return isX2many
                    ? elements.some((v) => offlineCompare(pick(v), operator, target))
                    : offlineCompare(value ? pick(value) : false, operator, target);
            }
            if (op === "any" || op === "not any") {
                const related = isX2many ? elements : value ? [value] : [];
                const relation = field.relation;
                const sub = (v) =>
                    typeof v === "object"
                        ? offlineCompileDomain(target, model, relation)({ name: v.display_name, ...v })
                        : true;
                const found = related.some(sub);
                return op === "any" ? found : !found;
            }
            if (isX2many) {
                if (["=", "in", "child_of", "parent_of"].includes(op)) {
                    if (target === false || target === null) {
                        return !elements.length;
                    }
                    const targets = Array.isArray(target) ? target : [target];
                    if (targets.includes(false) && !elements.length) {
                        return true;
                    }
                    return elements.some((v) => targets.some((t) => offlineCompare(v, "=", t)));
                }
                if (["!=", "not in"].includes(op)) {
                    return !offlineCompileDomain([[name, op === "!=" ? "=" : "in", target]], model, modelName)(record);
                }
                if (op.includes("like")) {
                    const found = elements.some((v) => offlineCompare(v, op.replace("not ", ""), target));
                    return op.startsWith("not") ? !found : found;
                }
                return true;
            }
            return offlineCompare(value, operator, target);
        };
    }

    function parse() {
        const item = items[index++];
        if (item === "&") {
            const a = parse();
            const b = parse();
            return (r) => a(r) && b(r);
        }
        if (item === "|") {
            const a = parse();
            const b = parse();
            return (r) => a(r) || b(r);
        }
        if (item === "!") {
            const a = parse();
            return (r) => !a(r);
        }
        return leaf(item);
    }

    const parts = [];
    while (index < items.length) {
        parts.push(parse());
    }
    return (record) => parts.every((part) => part(record));
}

// ── Sorting ─────────────────────────────────────────────────────────────────

function offlineSortValue(value) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
        return value.display_name ?? value.id;
    }
    if (Array.isArray(value)) {
        return value.length;
    }
    return value;
}

function offlineSort(records, order, model) {
    const parts = String(order || model.meta?.order || "id")
        .split(",")
        .map((part) => part.trim().split(/\s+/))
        .filter(([name]) => name)
        .map(([name, direction = "asc", ...rest]) => ({
            name: name.replace(/"/g, ""),
            desc: direction.toLowerCase() === "desc",
            nulls: rest.join(" ").toLowerCase().replace("nulls ", "") || null,
        }));
    return [...records].sort((a, b) => {
        for (const { name, desc, nulls } of parts) {
            const va = offlineSortValue(a[name]);
            const vb = offlineSortValue(b[name]);
            const emptyA = va === false || va === null || va === undefined;
            const emptyB = vb === false || vb === null || vb === undefined;
            if (emptyA || emptyB) {
                if (emptyA && emptyB) {
                    continue;
                }
                // PostgreSQL: empty values last when ascending, first when descending.
                const emptyFirst = nulls ? nulls === "first" : desc;
                return emptyA === emptyFirst ? -1 : 1;
            }
            let result = 0;
            if (typeof va === "string" && typeof vb === "string") {
                result = va.localeCompare(vb, undefined, { sensitivity: "base" });
            } else {
                result = va < vb ? -1 : va > vb ? 1 : 0;
            }
            if (result) {
                return desc ? -result : result;
            }
        }
        return a.id - b.id;
    });
}

// ── Reading ─────────────────────────────────────────────────────────────────

function offlineEmptyValue(field, spec) {
    if (OFFLINE_X2MANY.has(field.type)) {
        return [];
    }
    if (OFFLINE_NUMBERS.has(field.type)) {
        return 0;
    }
    if (field.type === "properties") {
        return [];
    }
    return false;
}

/** A kept record, shaped for a web_read ``specification``. */
function offlineProject(stored, spec, model, modelName = model.model) {
    const fields = offlineFields(model, modelName);
    const result = { id: stored.id };
    for (const [name, fieldSpec = {}] of Object.entries(spec || {})) {
        if (name === "id") {
            continue;
        }
        const field = fields[name] || {};
        const value = stored[name];
        if (value === undefined || ["binary", "image"].includes(field.type)) {
            result[name] = offlineEmptyValue(field, fieldSpec);
        } else if (field.type === "many2one" || (value && typeof value === "object" && !Array.isArray(value))) {
            if (!value) {
                result[name] = false;
            } else if (fieldSpec.fields) {
                const related = { id: offlineId(value) };
                for (const sub of Object.keys(fieldSpec.fields)) {
                    related[sub] = typeof value === "object" && sub in value ? value[sub] : false;
                }
                result[name] = related;
            } else {
                result[name] = offlineId(value);
            }
        } else if (OFFLINE_X2MANY.has(field.type) || Array.isArray(value)) {
            const elements = Array.isArray(value) ? value : [];
            if (fieldSpec.fields) {
                const limit = fieldSpec.limit ?? Infinity;
                result[name] = elements.map((element, i) =>
                    i < limit && element && typeof element === "object"
                        ? offlineProject(element, fieldSpec.fields, model, field.relation)
                        : { id: offlineId(element) }
                );
            } else {
                result[name] = elements.map(offlineId);
            }
        } else {
            result[name] = value;
        }
    }
    return result;
}

/** A kept record, shaped like read() / search_read(): many2one as [id, name]. */
function offlineRead(stored, fieldNames, model) {
    const names = fieldNames && fieldNames.length ? fieldNames : Object.keys(stored);
    const fields = offlineFields(model);
    const result = { id: stored.id };
    for (const name of names) {
        const value = stored[name];
        const field = fields[name] || {};
        if (value === undefined) {
            result[name] = offlineEmptyValue(field, {});
        } else if (value && typeof value === "object" && !Array.isArray(value)) {
            result[name] = [value.id, value.display_name];
        } else if (Array.isArray(value)) {
            result[name] = value.map(offlineId);
        } else {
            result[name] = value;
        }
    }
    return result;
}

function offlineSearch(records, model, { domain, order, offset = 0, limit } = {}) {
    const matches = offlineSort(records.filter(offlineCompileDomain(domain, model)), order, model);
    const end = limit ? offset + limit : undefined;
    return { matches, page: matches.slice(offset, end) };
}

// ── Grouping ────────────────────────────────────────────────────────────────

const OFFLINE_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
];
const offlinePad = (n) => String(n).padStart(2, "0");

function offlineIsoWeek(date) {
    const target = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const day = target.getUTCDay() || 7;
    target.setUTCDate(target.getUTCDate() + 4 - day);
    const yearStart = new Date(Date.UTC(target.getUTCFullYear(), 0, 1));
    return { week: Math.ceil(((target - yearStart) / 86400000 + 1) / 7), year: target.getUTCFullYear() };
}

/** The group a date or timestamp falls in: [start, end, label], in local time. */
function offlineDateGroup(value, granularity, isDatetime) {
    const date = isDatetime ? new Date(String(value).replace(" ", "T") + "Z") : new Date(`${value}T00:00:00`);
    let start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    let end;
    let label;
    switch (granularity) {
        case "year":
            start = new Date(date.getFullYear(), 0, 1);
            end = new Date(date.getFullYear() + 1, 0, 1);
            label = String(start.getFullYear());
            break;
        case "quarter": {
            const quarter = Math.floor(date.getMonth() / 3);
            start = new Date(date.getFullYear(), quarter * 3, 1);
            end = new Date(date.getFullYear(), quarter * 3 + 3, 1);
            label = `Q${quarter + 1} ${start.getFullYear()}`;
            break;
        }
        case "week": {
            const day = (date.getDay() + 6) % 7; // Monday first
            start = new Date(date.getFullYear(), date.getMonth(), date.getDate() - day);
            end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 7);
            const { week, year } = offlineIsoWeek(start);
            label = `W${week} ${year}`;
            break;
        }
        case "day":
            end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 1);
            label = `${offlinePad(start.getDate())} ${OFFLINE_MONTHS[start.getMonth()].slice(0, 3)} ${start.getFullYear()}`;
            break;
        default: // month
            start = new Date(date.getFullYear(), date.getMonth(), 1);
            end = new Date(date.getFullYear(), date.getMonth() + 1, 1);
            label = `${OFFLINE_MONTHS[start.getMonth()]} ${start.getFullYear()}`;
    }
    const format = (d) =>
        isDatetime
            ? `${d.getUTCFullYear()}-${offlinePad(d.getUTCMonth() + 1)}-${offlinePad(d.getUTCDate())} ` +
              `${offlinePad(d.getUTCHours())}:${offlinePad(d.getUTCMinutes())}:${offlinePad(d.getUTCSeconds())}`
            : `${d.getFullYear()}-${offlinePad(d.getMonth() + 1)}-${offlinePad(d.getDate())}`;
    return [format(start), format(end), label];
}

/** Split records into groups for one ``groupby`` spec, like formatted_read_group. */
function offlineGroups(records, groupbySpec, aggregates, model) {
    const [path, granularity] = groupbySpec.split(":");
    const name = path.split(".")[0];
    const field = offlineFields(model)[name] || {};
    const buckets = new Map();
    const add = (key, value, extraDomain, record) => {
        if (!buckets.has(key)) {
            buckets.set(key, { value, extraDomain, records: [] });
        }
        buckets.get(key).records.push(record);
    };
    for (const record of records) {
        const value = record[name];
        if (field.type === "many2many" || Array.isArray(value)) {
            const elements = Array.isArray(value) ? value : [];
            if (!elements.length) {
                add("false", false, [[name, "not any", []]], record);
            }
            for (const element of elements) {
                add(`id:${offlineId(element)}`, [offlineId(element), offlineName(element)],
                    [[name, "=", offlineId(element)]], record);
            }
        } else if (field.type === "many2one" || (value && typeof value === "object")) {
            if (!value) {
                add("false", false, [[name, "=", false]], record);
            } else {
                add(`id:${value.id}`, [value.id, value.display_name], [[name, "=", value.id]], record);
            }
        } else if (["date", "datetime"].includes(field.type) && granularity) {
            if (!value) {
                add("false", false, [[name, "=", false]], record);
            } else {
                const [start, end, label] = offlineDateGroup(value, granularity, field.type === "datetime");
                add(`d:${start}`, [start, label], ["&", [name, ">=", start], [name, "<", end]], record);
            }
        } else {
            const key = value === undefined ? false : value;
            add(`v:${JSON.stringify(key)}`, key, [[name, "=", key]], record);
        }
    }
    const selectionOrder = (field.selection || []).map(([key]) => key);
    const groups = [...buckets.values()].sort((a, b) => {
        const emptyA = a.value === false || a.value === null;
        const emptyB = b.value === false || b.value === null;
        if (emptyA !== emptyB) {
            return emptyA ? 1 : -1;
        }
        const va = Array.isArray(a.value) ? a.value[0] : a.value;
        const vb = Array.isArray(b.value) ? b.value[0] : b.value;
        if (selectionOrder.length) {
            return selectionOrder.indexOf(va) - selectionOrder.indexOf(vb);
        }
        if (field.type === "many2one" || field.type === "many2many") {
            return va - vb; // the order the options were created in, near enough
        }
        return va < vb ? -1 : va > vb ? 1 : 0;
    });
    return groups.map((bucket) => {
        const group = { [groupbySpec]: bucket.value, __extra_domain: bucket.extraDomain };
        for (const aggregate of aggregates) {
            group[aggregate] = offlineAggregate(bucket.records, aggregate);
        }
        group.__count = bucket.records.length;
        Object.defineProperty(group, "__offline_records", { value: bucket.records, enumerable: false });
        return group;
    });
}

function offlineAggregate(records, aggregate) {
    if (aggregate === "__count") {
        return records.length;
    }
    const [name, operator = "sum"] = aggregate.split(":");
    const values = records.map((r) => offlineId(r[name])).filter((v) => v !== false && v !== null && v !== undefined);
    switch (operator) {
        case "sum":
            return values.reduce((a, b) => a + b, 0);
        case "avg":
            return values.length ? values.reduce((a, b) => a + b, 0) / values.length : false;
        case "min":
            return values.length ? values.reduce((a, b) => (b < a ? b : a)) : false;
        case "max":
            return values.length ? values.reduce((a, b) => (b > a ? b : a)) : false;
        case "count":
            return values.length;
        case "count_distinct":
            return new Set(values).size;
        case "bool_and":
            return values.every(Boolean);
        case "bool_or":
            return values.some(Boolean);
        default:
            return false;
    }
}

/** web_read_group: groups, with the records of open groups, like the server. */
function offlineWebReadGroup(records, model, kwargs) {
    const groupby = kwargs.groupby || [];
    const aggregates = [...(kwargs.aggregates || [])];
    if (!aggregates.includes("__count")) {
        aggregates.push("__count");
    }
    const matching = records.filter(offlineCompileDomain(kwargs.domain, model));
    const spec = kwargs.unfold_read_specification || {};
    const defaultLimit = kwargs.unfold_read_default_limit ?? 80;

    function open(groups, level, autoUnfold, openingInfo) {
        const infoByValue = new Map((openingInfo || []).map((info) => [info.value, info]));
        const lastLevel = level === groupby.length - 1;
        const field = offlineFields(model)[groupby[level].split(":")[0].split(".")[0]] || {};
        let opened = 0;
        for (const group of groups) {
            const value = group[groupby[level]];
            const raw = Array.isArray(value) ? value[0] : value;
            let limit = defaultLimit;
            let offset = 0;
            let subOpening = null;
            if (openingInfo && infoByValue.has(raw)) {
                const info = infoByValue.get(raw);
                if (info.folded) {
                    continue;
                }
                limit = info.limit;
                offset = info.offset || 0;
                subOpening = info.groups || null;
            } else if (!autoUnfold || opened >= OFFLINE_MAX_OPENED_GROUPS || (field.relation && !value)) {
                continue;
            }
            opened++;
            const groupRecords = group.__offline_records;
            if (lastLevel) {
                const sorted = offlineSort(groupRecords, kwargs.order, model);
                group.__records = sorted
                    .slice(offset, limit ? offset + limit : undefined)
                    .map((record) => offlineProject(record, spec, model));
            } else {
                const subgroups = offlineGroups(groupRecords, groupby[level + 1], aggregates, model);
                group.__groups = { groups: subgroups, length: subgroups.length };
                open(subgroups, level + 1, false, subOpening);
            }
        }
    }

    const all = offlineGroups(matching, groupby[0], aggregates, model);
    const offset = kwargs.offset || 0;
    const groups = all.slice(offset, kwargs.limit ? offset + kwargs.limit : undefined);
    open(groups, 0, Boolean(kwargs.auto_unfold), kwargs.opening_info);
    return { groups, length: all.length };
}

// ── Requests ────────────────────────────────────────────────────────────────

class OfflineUnavailable extends Error {}

/** Answer an ORM call from the kept records, or throw OfflineUnavailable. */
function offlineCallKw(method, args, kwargs, model, records) {
    args = args || [];
    kwargs = kwargs || {};
    const byId = new Map(records.map((record) => [record.id, record]));
    const find = (ids) => {
        const missing = ids.filter((id) => !byId.has(id));
        if (missing.length) {
            throw new OfflineUnavailable("This record isn't saved on this device.");
        }
        return ids.map((id) => byId.get(id));
    };
    switch (method) {
        case "web_search_read": {
            const { matches, page } = offlineSearch(records, model, {
                domain: kwargs.domain ?? args[0],
                order: kwargs.order,
                offset: kwargs.offset || 0,
                limit: kwargs.limit,
            });
            return {
                length: matches.length,
                records: page.map((record) => offlineProject(record, kwargs.specification ?? args[1], model)),
            };
        }
        case "web_read":
            return find(args[0] || []).map((record) => offlineProject(record, kwargs.specification ?? args[1], model));
        case "read":
            return find(args[0] || []).map((record) => offlineRead(record, kwargs.fields ?? args[1], model));
        case "search_read": {
            const { page } = offlineSearch(records, model, {
                domain: kwargs.domain ?? args[0],
                order: kwargs.order,
                offset: kwargs.offset || 0,
                limit: kwargs.limit,
            });
            return page.map((record) => offlineRead(record, kwargs.fields ?? args[1], model));
        }
        case "search":
            return offlineSearch(records, model, {
                domain: kwargs.domain ?? args[0],
                order: kwargs.order,
                offset: kwargs.offset || 0,
                limit: kwargs.limit,
            }).page.map((record) => record.id);
        case "search_count":
            return records.filter(offlineCompileDomain(kwargs.domain ?? args[0], model)).length;
        case "web_read_group":
            return offlineWebReadGroup(records, model, kwargs);
        case "formatted_read_group": {
            const matching = records.filter(offlineCompileDomain(kwargs.domain ?? args[0], model));
            const groupby = kwargs.groupby || [];
            const aggregates = kwargs.aggregates || ["__count"];
            return offlineGroups(matching, groupby[0], aggregates, model);
        }
        case "name_search":
        case "web_name_search": {
            const name = kwargs.name ?? args[0] ?? "";
            const domain = [...(kwargs.domain || kwargs.args || []), ["display_name", kwargs.operator || "ilike", name]];
            const { page } = offlineSearch(records, model, { domain, limit: kwargs.limit || 8 });
            if (method === "name_search") {
                return page.map((record) => [record.id, record.display_name]);
            }
            const spec = kwargs.specification || { display_name: {} };
            return page.map((record) => ({
                ...offlineProject(record, spec, model),
                __formatted_display_name: record.display_name,
            }));
        }
        case "read_progress_bar":
            return {};
        case "get_formview_id":
            return false;
        case "get_formview_action": {
            const [id] = args[0] || [];
            find([id]);
            return {
                type: "ir.actions.act_window",
                res_model: model.model,
                res_id: id,
                views: [[false, "form"]],
                target: "current",
                context: kwargs.context || {},
            };
        }
        case "get_views":
            return offlineGetViews(model, kwargs.views ?? args[0] ?? [], kwargs.options || {});
        default:
            throw new OfflineUnavailable();
    }
}

/** get_views from the views kept with the model. */
function offlineGetViews(model, requested, options) {
    const bundles = model.meta?.bundles || [];
    const views = {};
    for (const [viewId, viewType] of requested) {
        const found =
            bundles.find((b) => b.action_id === (options.action_id || false) &&
                b.views.some(([id, type]) => type === viewType && (id || false) === (viewId || false))) ||
            bundles.find((b) => b.views.some(([id, type]) => type === viewType && (id || false) === (viewId || false))) ||
            bundles.find((b) => b.result.views[viewType]);
        if (!found || !found.result.views[viewType]) {
            throw new OfflineUnavailable();
        }
        views[viewType] = found.result.views[viewType];
    }
    return { views, models: model.meta.models };
}

/** /web/action/load for the actions kept with the models. */
function offlineLoadAction(models, actionId) {
    for (const model of models) {
        for (const action of model.meta?.actions || []) {
            if (action.id === actionId || String(action.id) === String(actionId) ||
                    action.xml_id === actionId || (action.path && action.path === actionId)) {
                return action;
            }
        }
    }
    throw new OfflineUnavailable();
}

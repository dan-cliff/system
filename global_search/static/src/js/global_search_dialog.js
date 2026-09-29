/** @odoo-module **/
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { rpc } from "@web/core/network/rpc";

// ── Date preset definitions ────────────────────────────────────────────────────
const DATE_PRESETS = [
    { value: "any",        label: "Any Time" },
    { value: "today",      label: "Today" },
    { value: "this_week",  label: "This Week" },
    { value: "this_month", label: "This Month" },
    { value: "this_year",  label: "This Year" },
    { value: "last_7",     label: "Last 7 Days" },
    { value: "last_30",    label: "Last 30 Days" },
    { value: "last_90",    label: "Last 90 Days" },
    { value: "custom",     label: "Custom Range…" },
];

/** Format a JS Date to YYYY-MM-DD for the backend. */
function toISODate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
}

/** Compute { from, to } strings for a preset relative date range. */
function getPresetRange(preset) {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    switch (preset) {
        case "today":
            return { from: toISODate(today), to: toISODate(today) };

        case "this_week": {
            const start = new Date(today);
            start.setDate(today.getDate() - today.getDay());
            return { from: toISODate(start), to: toISODate(today) };
        }
        case "this_month": {
            const start = new Date(today.getFullYear(), today.getMonth(), 1);
            return { from: toISODate(start), to: toISODate(today) };
        }
        case "this_year": {
            const start = new Date(today.getFullYear(), 0, 1);
            return { from: toISODate(start), to: toISODate(today) };
        }
        case "last_7": {
            const start = new Date(today);
            start.setDate(today.getDate() - 6);
            return { from: toISODate(start), to: toISODate(today) };
        }
        case "last_30": {
            const start = new Date(today);
            start.setDate(today.getDate() - 29);
            return { from: toISODate(start), to: toISODate(today) };
        }
        case "last_90": {
            const start = new Date(today);
            start.setDate(today.getDate() - 89);
            return { from: toISODate(start), to: toISODate(today) };
        }
        default:
            return { from: null, to: null };
    }
}

// ── Badge colour palette (keyed by consistent model hash) ─────────────────────
const BADGE_CLASSES = [
    "gs-badge-blue",
    "gs-badge-green",
    "gs-badge-red",
    "gs-badge-orange",
    "gs-badge-teal",
    "gs-badge-purple",
    "gs-badge-pink",
    "gs-badge-indigo",
];

function modelBadgeClass(model) {
    let hash = 0;
    for (let i = 0; i < model.length; i++) {
        hash = ((hash << 5) - hash) + model.charCodeAt(i);
        hash |= 0;
    }
    return BADGE_CLASSES[Math.abs(hash) % BADGE_CLASSES.length];
}

// ── Dialog component ──────────────────────────────────────────────────────────
export class GlobalSearchDialog extends Component {
    static template = "global_search.GlobalSearchDialog";
    static components = { Dialog };
    static props = { close: Function };

    setup() {
        this.searchRef = useRef("searchInput");

        this.state = useState({
            query: "",
            modelFilter: "",
            datePreset: "any",
            dateFrom: "",
            dateTo: "",
            results: [],
            total: 0,
            loading: false,
            models: [],
            modelsLoaded: false,
            searched: false,
            error: null,
        });

        this._searchTimer = null;

        onMounted(async () => {
            this.searchRef.el?.focus();
            await this._loadModels();
        });

        onWillUnmount(() => {
            if (this._searchTimer) {
                clearTimeout(this._searchTimer);
            }
        });
    }

    // ── Computed getters ───────────────────────────────────────────────────────
    get datePresets() { return DATE_PRESETS; }
    get showCustomRange() { return this.state.datePreset === "custom"; }

    // ── Internal helpers ───────────────────────────────────────────────────────
    async _loadModels() {
        try {
            const models = await rpc("/global_search/get_models", {});
            this.state.models = models || [];
        } catch (e) {
            console.error("GlobalSearch: failed to load model list", e);
        } finally {
            this.state.modelsLoaded = true;
        }
    }

    _scheduleSearch(delay = 400) {
        if (this._searchTimer) clearTimeout(this._searchTimer);
        if (this.state.query.length >= 2) {
            this._searchTimer = setTimeout(() => this._doSearch(), delay);
        } else {
            this.state.results = [];
            this.state.searched = false;
        }
    }

    async _doSearch() {
        const query = this.state.query.trim();
        if (query.length < 2) return;

        // Resolve date range
        let dateFrom = null;
        let dateTo   = null;
        if (this.state.datePreset === "custom") {
            dateFrom = this.state.dateFrom  || null;
            dateTo   = this.state.dateTo    || null;
        } else if (this.state.datePreset !== "any") {
            const range = getPresetRange(this.state.datePreset);
            dateFrom = range.from;
            dateTo   = range.to;
        }

        this.state.loading = true;
        this.state.error   = null;

        try {
            const resp = await rpc("/global_search/search", {
                query,
                model_filter: this.state.modelFilter || null,
                date_from:    dateFrom,
                date_to:      dateTo,
            });
            this.state.results = resp.results || [];
            this.state.total   = resp.total   || 0;
            this.state.searched = true;
        } catch (e) {
            this.state.error = "Search failed — please try again.";
            console.error("GlobalSearch: search error", e);
        } finally {
            this.state.loading = false;
        }
    }

    // ── Event handlers ─────────────────────────────────────────────────────────
    onQueryInput(ev) {
        this.state.query = ev.target.value;
        this._scheduleSearch();
    }

    onQueryKeydown(ev) {
        if (ev.key === "Enter") {
            if (this._searchTimer) clearTimeout(this._searchTimer);
            this._doSearch();
        } else if (ev.key === "Escape") {
            this.props.close();
        }
    }

    onModelChange(ev) {
        this.state.modelFilter = ev.target.value;
        if (this.state.searched) this._scheduleSearch(0);
    }

    onDatePresetChange(ev) {
        this.state.datePreset = ev.target.value;
        if (this.state.searched && this.state.datePreset !== "custom") {
            this._scheduleSearch(0);
        }
    }

    onDateFromChange(ev) { this.state.dateFrom = ev.target.value; }
    onDateToChange(ev)   { this.state.dateTo   = ev.target.value; }

    applyCustomDate() { this._doSearch(); }

    clearQuery() {
        this.state.query   = "";
        this.state.results = [];
        this.state.searched = false;
        this.searchRef.el?.focus();
    }

    // ── URL / badge helpers ────────────────────────────────────────────────────
    getRecordUrl(result) {
        if (!result.action_id) return null;
        // active_id must be included so that action contexts that reference
        // active_id (e.g. Studio-generated domain/context expressions) can
        // be evaluated without raising an EvalError.
        return `/web#action=${result.action_id}&id=${result.id}&view_type=form&active_id=${result.id}`;
    }

    badgeClass(model) { return modelBadgeClass(model); }
}

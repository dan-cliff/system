/** @odoo-module **/
/**
 * Training Sessions Report — OWL Client Action
 *
 * Renders a scrollable table of lms.course.session records with filters
 * for Course, Instructor, Status, Self-Enrolment, and Start Date range.
 * Includes PDF and Excel export.
 */

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// ── Session state config ──────────────────────────────────────────────────────
const SESSION_STATE_CONFIG = {
    draft:       { label: "Draft",               cssClass: "lms-sess-draft"       },
    open:        { label: "Open for Enrolment",  cssClass: "lms-sess-open"        },
    full:        { label: "Full",                 cssClass: "lms-sess-full"        },
    closed:      { label: "Closed for Enrolment", cssClass: "lms-sess-closed"      },
    in_progress: { label: "In Progress",          cssClass: "lms-sess-in-progress" },
    completed:   { label: "Completed",            cssClass: "lms-sess-completed"   },
    cancelled:   { label: "Cancelled",            cssClass: "lms-sess-cancelled"   },
};

const SESSION_STATUSES = [
    { value: "",           label: "All Statuses"       },
    { value: "draft",      label: "Draft"               },
    { value: "open",       label: "Open for Enrolment"  },
    { value: "full",        label: "Full"                 },
    { value: "closed",      label: "Closed for Enrolment"},
    { value: "in_progress", label: "In Progress"         },
    { value: "completed",  label: "Completed"           },
    { value: "cancelled",  label: "Cancelled"           },
];

const SELF_ENROL_OPTIONS = [
    { value: "",    label: "Any Self-Enrolment" },
    { value: "yes", label: "Self-Enrolment On"  },
    { value: "no",  label: "Self-Enrolment Off" },
];

const START_DATE_OPTIONS = [
    { value: "",               label: "Any Start Date"           },
    { value: "today",          label: "Today"                    },
    { value: "tomorrow",       label: "Tomorrow"                 },
    { value: "next_7_days",    label: "Next 7 Days"              },
    { value: "next_30_days",   label: "Next 30 Days"             },
    { value: "next_cal_month", label: "Next Calendar Month"      },
    { value: "rest_of_year",   label: "Remainder of This Year"   },
    { value: "next_cal_year",  label: "Next Calendar Year"       },
    { value: "custom",         label: "Custom Date Range\u2026"  },
];

// ── Component ─────────────────────────────────────────────────────────────────
class LmsSessionsReport extends Component {
    static template = "learning_management.LmsSessionsReport";

    setup() {
        this.orm           = useService("orm");
        this.actionService = useService("action");

        this.stateConfig       = SESSION_STATE_CONFIG;
        this.sessionStatuses   = SESSION_STATUSES;
        this.selfEnrolOptions  = SELF_ENROL_OPTIONS;
        this.startDateOptions  = START_DATE_OPTIONS;

        this.state = useState({
            loading:         true,
            records:         [],
            allCourses:      [],
            allInstructors:  [],
            // filters
            courseFilter:    "",
            instructorFilter:"",
            statusFilter:    "",
            selfEnrolFilter: "",
            startDateOption: "",
            startDateFrom:   "",
            startDateTo:     "",
        });

        onWillStart(async () => {
            const [courses, instructors] = await Promise.all([
                this.orm.searchRead(
                    "lms.course",
                    [["active", "=", true]],
                    ["id", "name"],
                    { order: "name" },
                ),
                this.orm.searchRead(
                    "hr.employee",
                    [["active", "=", true]],
                    ["id", "name"],
                    { order: "name" },
                ),
            ]);
            this.state.allCourses     = courses;
            this.state.allInstructors = instructors;
            await this._loadData();
        });
    }

    // ── Date helpers ──────────────────────────────────────────────────────────

    _fmt(d) {
        const y  = d.getFullYear();
        const m  = String(d.getMonth() + 1).padStart(2, "0");
        const dd = String(d.getDate()).padStart(2, "0");
        return `${y}-${m}-${dd}`;
    }

    _startDateDomain(option, from, to) {
        if (!option) return [];

        const today = new Date();
        today.setHours(0, 0, 0, 0);

        const fmt    = (d) => this._fmt(d);
        const gte    = (v) => ["date_start", ">=", v];
        const lte    = (v) => ["date_start", "<=", v];

        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);

        switch (option) {
            case "today": {
                return [gte(fmt(today)), lte(fmt(today) + " 23:59:59")];
            }
            case "tomorrow": {
                return [gte(fmt(tomorrow)), lte(fmt(tomorrow) + " 23:59:59")];
            }
            case "next_7_days": {
                const end = new Date(today);
                end.setDate(end.getDate() + 7);
                return [gte(fmt(today)), lte(fmt(end))];
            }
            case "next_30_days": {
                const end = new Date(today);
                end.setDate(end.getDate() + 30);
                return [gte(fmt(today)), lte(fmt(end))];
            }
            case "next_cal_month": {
                const nm = today.getMonth() + 1; // next month (0-indexed + 1 = 1-indexed of next)
                const ny = nm === 12 ? today.getFullYear() + 1 : today.getFullYear();
                const nm2 = nm === 12 ? 0 : nm;   // 0-indexed month for next month
                const start = new Date(ny, nm2, 1);
                const end   = new Date(ny, nm2 + 1, 0); // last day of next month
                return [gte(fmt(start)), lte(fmt(end))];
            }
            case "rest_of_year": {
                const yearEnd = new Date(today.getFullYear(), 11, 31);
                return [gte(fmt(today)), lte(fmt(yearEnd))];
            }
            case "next_cal_year": {
                const ny = today.getFullYear() + 1;
                return [gte(`${ny}-01-01`), lte(`${ny}-12-31`)];
            }
            case "custom": {
                const clauses = [];
                if (from) clauses.push(gte(from));
                if (to)   clauses.push(lte(to));
                return clauses;
            }
            default: return [];
        }
    }

    // ── Data loading ──────────────────────────────────────────────────────────

    async _loadData() {
        this.state.loading = true;
        const domain = [];

        if (this.state.courseFilter)
            domain.push(["course_id", "=", parseInt(this.state.courseFilter)]);
        if (this.state.instructorFilter)
            domain.push(["instructor_id", "=", parseInt(this.state.instructorFilter)]);
        if (this.state.statusFilter)
            domain.push(["state", "=", this.state.statusFilter]);
        if (this.state.selfEnrolFilter === "yes")
            domain.push(["is_public", "=", true]);
        if (this.state.selfEnrolFilter === "no")
            domain.push(["is_public", "=", false]);

        domain.push(...this._startDateDomain(
            this.state.startDateOption,
            this.state.startDateFrom,
            this.state.startDateTo,
        ));

        const records = await this.orm.call(
            "lms.course.session",
            "get_sessions_report_data",
            [domain],
        );
        this.state.records = records;
        this.state.loading  = false;
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    formatDateTime(str) {
        if (!str) return "";
        const [d, t] = str.split("T");
        if (!d) return "";
        const [y, m, dd] = d.split("-");
        return `${dd}/${m}/${y}${t ? " " + t : ""}`;
    }

    stateClass(state) {
        return (SESSION_STATE_CONFIG[state] || {}).cssClass || "";
    }

    stateLabel(state) {
        return (SESSION_STATE_CONFIG[state] || {}).label || state;
    }

    // ── Summary stats ─────────────────────────────────────────────────────────

    get stats() {
        const r = this.state.records;
        return {
            total:    r.length,
            upcoming: r.filter(x => x.state === "open" || x.state === "draft").length,
            full:     r.filter(x => x.state === "full").length,
            completed:r.filter(x => x.state === "completed").length,
        };
    }

    // ── Navigation ────────────────────────────────────────────────────────────

    openRecord(rec) {
        this.actionService.doAction({
            type:      "ir.actions.act_window",
            res_model: "lms.course.session",
            res_id:    rec.id,
            views:     [[false, "form"]],
            target:    "current",
        });
    }

    openCourse(ev, rec) {
        ev.stopPropagation();
        this.actionService.doAction({
            type:      "ir.actions.act_window",
            res_model: "lms.course",
            res_id:    rec.course_id,
            views:     [[false, "form"]],
            target:    "current",
        });
    }

    // ── Export ────────────────────────────────────────────────────────────────

    _currentDomain() {
        const domain = [];
        if (this.state.courseFilter)
            domain.push(["course_id", "=", parseInt(this.state.courseFilter)]);
        if (this.state.instructorFilter)
            domain.push(["instructor_id", "=", parseInt(this.state.instructorFilter)]);
        if (this.state.statusFilter)
            domain.push(["state", "=", this.state.statusFilter]);
        if (this.state.selfEnrolFilter === "yes")
            domain.push(["is_public", "=", true]);
        if (this.state.selfEnrolFilter === "no")
            domain.push(["is_public", "=", false]);
        domain.push(...this._startDateDomain(
            this.state.startDateOption,
            this.state.startDateFrom,
            this.state.startDateTo,
        ));
        return domain;
    }

    exportPdf() {
        const url = `/learning/sessions/pdf?domain=${encodeURIComponent(JSON.stringify(this._currentDomain()))}`;
        window.open(url, "_blank");
    }

    exportExcel() {
        const url = `/learning/sessions/excel?domain=${encodeURIComponent(JSON.stringify(this._currentDomain()))}`;
        window.open(url, "_blank");
    }

    // ── Event handlers ────────────────────────────────────────────────────────

    async onCourseChange(ev)      { this.state.courseFilter     = ev.target.value; await this._loadData(); }
    async onInstructorChange(ev)  { this.state.instructorFilter = ev.target.value; await this._loadData(); }
    async onStatusChange(ev)      { this.state.statusFilter     = ev.target.value; await this._loadData(); }
    async onSelfEnrolChange(ev)   { this.state.selfEnrolFilter  = ev.target.value; await this._loadData(); }

    async onStartDateOptionChange(ev) {
        this.state.startDateOption = ev.target.value;
        if (ev.target.value !== "custom") {
            this.state.startDateFrom = "";
            this.state.startDateTo   = "";
        }
        await this._loadData();
    }

    async onStartDateFromChange(ev) { this.state.startDateFrom = ev.target.value; await this._loadData(); }
    async onStartDateToChange(ev)   { this.state.startDateTo   = ev.target.value; await this._loadData(); }
}

registry.category("actions").add("lms_sessions_report", LmsSessionsReport);

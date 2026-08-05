/** @odoo-module **/
/**
 * Training Records Expiring — Flat List Client Action
 *
 * Renders a scrollable table of training records sorted by expiry date
 * (soonest first, nulls last) with full filter support and PDF/Excel export.
 */

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// ── State display configuration ───────────────────────────────────────────────
const STATE_CONFIG = {
    completed:            { label: "Completed",            icon: "fa-check-circle"        },
    in_progress:          { label: "In Progress",          icon: "fa-circle"               },
    not_started:          { label: "Not Started",          icon: "fa-circle-o"             },
    pending_upload:       { label: "Pending Upload",       icon: "fa-upload"               },
    pending_verification: { label: "Pending Verification", icon: "fa-clock-o"              },
    failed:               { label: "Failed",               icon: "fa-times-circle"         },
    expired:              { label: "Expired",              icon: "fa-exclamation-triangle"  },
    lapsed:               { label: "Lapsed",               icon: "fa-ban"                   },
};

const COURSE_TYPES = [
    { value: "",              label: "All Types"     },
    { value: "licence",       label: "Licence"       },
    { value: "qualification", label: "Qualification" },
    { value: "training",      label: "Training"      },
    { value: "elearning",     label: "eLearning"     },
];

const STATUS_OPTIONS = [
    { value: "", label: "All Statuses" },
    ...Object.entries(STATE_CONFIG).map(([value, cfg]) => ({ value, label: cfg.label })),
];

const COMPLETED_OPTIONS = [
    { value: "",               label: "Any Completion Date"      },
    { value: "today",          label: "Completed Today"          },
    { value: "yesterday",      label: "Completed Yesterday"      },
    { value: "last_7_days",    label: "Completed Last 7 Days"    },
    { value: "wtd",            label: "Completed Week to Date"   },
    { value: "last_cal_week",  label: "Completed Last Cal. Week" },
    { value: "mtd",            label: "Completed Month to Date"  },
    { value: "last_month",     label: "Completed Last Month"     },
    { value: "last_cal_month", label: "Completed Last Cal. Month"},
    { value: "ytd",            label: "Completed Year to Date"   },
    { value: "last_year",      label: "Completed Last Year"      },
    { value: "custom",         label: "Custom Date Range…"       },
];

const EXPIRES_OPTIONS = [
    { value: "",            label: "Any Expiry Date"          },
    { value: "today",       label: "Expires Today"            },
    { value: "tomorrow",    label: "Expires Tomorrow"         },
    { value: "next_7_days", label: "Expires Next 7 Days"      },
    { value: "next_month",  label: "Expires Next Month"       },
    { value: "next_year",   label: "Expires Next Year"        },
    { value: "this_year",   label: "Expires This Year"        },
    { value: "custom",      label: "Custom Date Range…"       },
];

// ── Component ─────────────────────────────────────────────────────────────────
export class LmsExpiringReport extends Component {
    static template = "learning_management.LmsExpiringReport";
    static props = ["*"];

    setup() {
        this.orm           = useService("orm");
        this.actionService = useService("action");

        this.stateConfig       = STATE_CONFIG;
        this.courseTypes       = COURSE_TYPES;
        this.statusOptions     = STATUS_OPTIONS;
        this.completedOptions  = COMPLETED_OPTIONS;
        this.expiresOptions    = EXPIRES_OPTIONS;

        this.state = useState({
            loading:          true,
            records:          [],
            allCourses:       [],
            allEmployees:     [],
            allDepartments:   [],
            allCompanies:     [],
            // filters
            courseTypeFilter:  "",
            statusFilter:      "",
            courseFilter:      "",
            employeeFilter:    "",
            departmentFilter:  "",
            companyFilter:     "",
            completedOption:  "",
            completedFrom:    "",
            completedTo:      "",
            expiresOption:    "",
            expiresFrom:      "",
            expiresTo:        "",
        });

        onWillStart(async () => {
            const [courses, employees, departments, companies] = await Promise.all([
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
                this.orm.searchRead(
                    "hr.department",
                    [],
                    ["id", "name"],
                    { order: "name" },
                ),
                this.orm.searchRead(
                    "res.company",
                    [],
                    ["id", "name"],
                    { order: "name" },
                ),
            ]);
            this.state.allCourses     = courses;
            this.state.allEmployees   = employees;
            this.state.allDepartments = departments;
            this.state.allCompanies   = companies;
            await this._loadData();
        });
    }

    // ── Date helpers ──────────────────────────────────────────────────────────

    _fmt(d) {
        const yyyy = d.getFullYear();
        const mm   = String(d.getMonth() + 1).padStart(2, "0");
        const dd   = String(d.getDate()).padStart(2, "0");
        return `${yyyy}-${mm}-${dd}`;
    }

    _addDays(d, n) {
        const r = new Date(d);
        r.setDate(r.getDate() + n);
        return r;
    }

    _dateDomain(field, option, from, to) {
        if (!option) return [];

        const today = new Date();
        today.setHours(0, 0, 0, 0);

        const dow = today.getDay();
        const thisMonday = this._addDays(today, dow === 0 ? -6 : 1 - dow);
        const lastMonday = this._addDays(thisMonday, -7);
        const lastSunday = this._addDays(thisMonday, -1);

        const monthStart     = new Date(today.getFullYear(), today.getMonth(), 1);
        const lastMonthEnd   = new Date(monthStart.getTime() - 86400000);
        const lastMonthStart = new Date(lastMonthEnd.getFullYear(), lastMonthEnd.getMonth(), 1);

        const yearStart = new Date(today.getFullYear(), 0, 1);
        const yearEnd   = new Date(today.getFullYear(), 11, 31);

        const gte = (d) => [field, ">=", this._fmt(d)];
        const lte = (d) => [field, "<=", this._fmt(d)];
        const eq  = (d) => [field, "=",  this._fmt(d)];

        switch (option) {
            case "today":          return [eq(today)];
            case "yesterday":      return [eq(this._addDays(today, -1))];
            case "tomorrow":       return [eq(this._addDays(today,  1))];
            case "last_7_days":    return [gte(this._addDays(today, -7)),    lte(today)];
            case "wtd":            return [gte(thisMonday),                  lte(today)];
            case "last_cal_week":  return [gte(lastMonday),                  lte(lastSunday)];
            case "mtd":            return [gte(monthStart),                  lte(today)];
            case "last_month":     return [gte(this._addDays(today, -30)),   lte(today)];
            case "last_cal_month": return [gte(lastMonthStart),              lte(lastMonthEnd)];
            case "ytd":            return [gte(yearStart),                   lte(today)];
            case "last_year":      return [gte(this._addDays(today, -365)),  lte(today)];
            case "next_7_days":    return [gte(today), lte(this._addDays(today,  7))];
            case "next_month":     return [gte(today), lte(this._addDays(today, 30))];
            case "next_year":      return [gte(today), lte(this._addDays(today, 365))];
            case "this_year":      return [gte(yearStart), lte(yearEnd)];
            case "custom": {
                const clauses = [];
                if (from) clauses.push([field, ">=", from]);
                if (to)   clauses.push([field, "<=", to]);
                return clauses;
            }
            default: return [];
        }
    }

    // ── Data loading ──────────────────────────────────────────────────────────

    _buildDomain() {
        const domain = [];

        if (this.state.courseTypeFilter)
            domain.push(["course_type", "=", this.state.courseTypeFilter]);
        if (this.state.statusFilter)
            domain.push(["state", "=", this.state.statusFilter]);
        if (this.state.courseFilter)
            domain.push(["course_id", "=", parseInt(this.state.courseFilter)]);
        if (this.state.employeeFilter)
            domain.push(["employee_id", "=", parseInt(this.state.employeeFilter)]);
        if (this.state.departmentFilter)
            domain.push(["employee_id.department_id", "=", parseInt(this.state.departmentFilter)]);
        if (this.state.companyFilter)
            domain.push(["employee_id.company_id", "=", parseInt(this.state.companyFilter)]);

        domain.push(...this._dateDomain(
            "completion_date",
            this.state.completedOption,
            this.state.completedFrom,
            this.state.completedTo,
        ));
        domain.push(...this._dateDomain(
            "expiry_date",
            this.state.expiresOption,
            this.state.expiresFrom,
            this.state.expiresTo,
        ));

        return domain;
    }

    async _loadData() {
        this.state.loading = true;
        const domain = this._buildDomain();
        const records = await this.orm.call(
            "lms.employee.record",
            "get_expiring_report_data",
            [domain],
        );
        this.state.records = records;
        this.state.loading = false;
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    formatDate(dateStr) {
        if (!dateStr) return "";
        const [y, m, d] = dateStr.split("-");
        return `${d}/${m}/${y}`;
    }

    /** Convert snake_case course type to Title Case for display. */
    formatCourseType(courseType) {
        if (!courseType) return "";
        return courseType.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
    }

    /** Return CSS class for the Expires On cell based on days until expiry. */
    expiryClass(dateStr) {
        if (!dateStr) return "lms-exp-no-date";
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const exp   = new Date(dateStr);
        const delta = Math.round((exp - today) / 86400000);
        if (delta < 0)   return "lms-exp-overdue";
        if (delta <= 30) return "lms-exp-soon";
        if (delta <= 90) return "lms-exp-warning";
        return "lms-exp-ok";
    }

    // ── Event handlers ────────────────────────────────────────────────────────

    async onCourseTypeChange(ev) {
        this.state.courseTypeFilter = ev.target.value;
        await this._loadData();
    }

    async onStatusChange(ev) {
        this.state.statusFilter = ev.target.value;
        await this._loadData();
    }

    async onCourseChange(ev) {
        this.state.courseFilter = ev.target.value;
        await this._loadData();
    }

    async onEmployeeChange(ev) {
        this.state.employeeFilter = ev.target.value;
        await this._loadData();
    }

    async onDepartmentChange(ev) {
        this.state.departmentFilter = ev.target.value;
        await this._loadData();
    }

    async onCompanyChange(ev) {
        this.state.companyFilter = ev.target.value;
        await this._loadData();
    }

    async onCompletedOptionChange(ev) {
        this.state.completedOption = ev.target.value;
        if (ev.target.value !== "custom") {
            this.state.completedFrom = "";
            this.state.completedTo   = "";
        }
        await this._loadData();
    }

    async onCompletedFromChange(ev) {
        this.state.completedFrom = ev.target.value;
        await this._loadData();
    }

    async onCompletedToChange(ev) {
        this.state.completedTo = ev.target.value;
        await this._loadData();
    }

    async onExpiresOptionChange(ev) {
        this.state.expiresOption = ev.target.value;
        if (ev.target.value !== "custom") {
            this.state.expiresFrom = "";
            this.state.expiresTo   = "";
        }
        await this._loadData();
    }

    async onExpiresFromChange(ev) {
        this.state.expiresFrom = ev.target.value;
        await this._loadData();
    }

    async onExpiresToChange(ev) {
        this.state.expiresTo = ev.target.value;
        await this._loadData();
    }

    openRecord(rec) {
        this.actionService.doAction({
            type:      "ir.actions.act_window",
            res_model: "lms.employee.record",
            res_id:    rec.id,
            views:     [[false, "form"]],
            target:    "current",
        });
    }

    openEmployee(ev, rec) {
        ev.stopPropagation();
        this.actionService.doAction({
            type:      "ir.actions.act_window",
            res_model: "hr.employee",
            res_id:    rec.employee_id,
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

    exportPdf() {
        const domain = this._buildDomain();
        const url = `/learning/expiring/pdf?domain=${encodeURIComponent(JSON.stringify(domain))}`;
        window.open(url, "_blank");
    }

    exportExcel() {
        const domain = this._buildDomain();
        const url = `/learning/expiring/excel?domain=${encodeURIComponent(JSON.stringify(domain))}`;
        window.open(url, "_blank");
    }

    // ── Summary stats ─────────────────────────────────────────────────────────

    get stats() {
        const today   = new Date();
        today.setHours(0, 0, 0, 0);
        const records = this.state.records;
        const total   = records.length;
        let expired   = 0;
        let soon      = 0;
        let valid     = 0;

        for (const rec of records) {
            if (!rec.expiry_date) continue;
            const exp   = new Date(rec.expiry_date);
            const delta = Math.round((exp - today) / 86400000);
            if (delta < 0)        expired++;
            else if (delta <= 30) soon++;
            else                  valid++;
        }

        return { total, expired, soon, valid };
    }
}

registry.category("actions").add("lms_expiring_report", LmsExpiringReport);

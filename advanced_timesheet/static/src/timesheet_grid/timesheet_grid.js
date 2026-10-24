import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatFloatTime } from "@web/views/fields/formatters";
import { parseFloatTime } from "@web/views/fields/parsers";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

const { DateTime } = luxon;

/**
 * The timesheet's period as a grid, like Odoo's Timesheets grid: a row per
 * project / task (plus rows filled in automatically, e.g. from Attendances),
 * a column per day grouped into weeks. Typing hours in a cell saves at once
 * (the server adjusts that row's entries for the day).
 */
export class TimesheetGrid extends Component {
    static template = "advanced_timesheet.TimesheetGrid";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = useState({ data: null, busy: false });
        this.signature = this.recordSignature(this.props.record);
        onWillStart(() => this.load(this.props.record));
        onWillUpdateProps(async (nextProps) => {
            const signature = this.recordSignature(nextProps.record);
            if (signature !== this.signature) {
                this.signature = signature;
                await this.load(nextProps.record);
            }
        });
    }

    /** Changes when the timesheet is saved, reloaded or opened on another record. */
    recordSignature(record) {
        const data = record.data;
        return [
            record.resId,
            data.state,
            data.date_start,
            data.date_end,
            data.total_hours,
            data.line_ids?.currentIds?.join(","),
        ].join("|");
    }

    async load(record) {
        if (!record.resId) {
            this.state.data = null;
            return;
        }
        this.state.data = await this.orm.call("advanced.timesheet", "get_grid_data", [[record.resId]]);
    }

    async reload() {
        const record = this.props.record;
        await record.load();
        this.signature = this.recordSignature(record);
        await this.load(record);
    }

    // ------------------------------------------------------------------
    // Display
    // ------------------------------------------------------------------
    get readonly() {
        return this.props.readonly || !this.state.data?.editable;
    }

    day(iso) {
        return DateTime.fromISO(iso);
    }

    weekdayLabel(iso) {
        return this.day(iso).toFormat("ccc");
    }

    dateLabel(iso) {
        return this.day(iso).toFormat("dd/MM/yyyy");
    }

    isWeekend(iso) {
        return this.day(iso).weekday > 5;
    }

    hours(value) {
        return value ? formatFloatTime(value) : "";
    }

    cellValue(row, iso) {
        return row.cells[iso] || 0;
    }

    dayTotal(iso) {
        return this.state.data.rows.reduce((total, row) => total + this.cellValue(row, iso), 0);
    }

    weekTotal(week) {
        return week.days.reduce((total, iso) => total + this.dayTotal(iso), 0);
    }

    get grandTotal() {
        return this.state.data.rows.reduce((total, row) => total + row.total, 0);
    }

    cellClass(iso) {
        return {
            o_timesheet_grid_weekend: this.isWeekend(iso),
            o_timesheet_grid_today: iso === this.state.data.today,
            o_timesheet_grid_week_start: this.state.data.weeks.some((week) => week.days[0] === iso),
        };
    }

    // ------------------------------------------------------------------
    // Editing
    // ------------------------------------------------------------------
    onFocus(ev) {
        ev.target.select();
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.target.blur();
        } else if (ev.key === "Escape") {
            ev.target.value = ev.target.dataset.value;
            ev.target.blur();
        }
    }

    async onCellChange(row, iso, ev) {
        const text = ev.target.value.trim();
        let hours = 0;
        if (text) {
            try {
                hours = parseFloatTime(text);
            } catch {
                hours = NaN;
            }
        }
        if (isNaN(hours) || hours < 0 || hours > 24) {
            this.notification.add(_t("Enter the hours as 7.5 or 7:30 (0 to 24)."), { type: "danger" });
            ev.target.value = ev.target.dataset.value;
            return;
        }
        this.state.busy = true;
        try {
            // Unsaved changes (e.g. on the Entries tab) go first, as the grid works on saved entries.
            if (!(await this.props.record.save())) {
                ev.target.value = ev.target.dataset.value;
                return;
            }
            await this.orm.call("advanced.timesheet", "set_grid_cell", [
                [this.props.record.resId],
                { project_id: row.project_id, task_id: row.task_id, is_auto: row.is_auto },
                iso,
                hours,
            ]);
        } finally {
            await this.reload();
            this.state.busy = false;
        }
    }

    async onAddLine() {
        const record = this.props.record;
        if (!(await record.save()) || !record.resId) {
            return;
        }
        const { days, today } = this.state.data || {};
        this.dialog.add(FormViewDialog, {
            resModel: "advanced.timesheet.line",
            title: _t("Add a Line"),
            context: {
                default_sheet_id: record.resId,
                default_date: days?.includes(today) ? today : days?.[0] || record.data.date_start,
                form_view_ref: "advanced_timesheet.advanced_timesheet_line_view_form",
            },
            onRecordSaved: () => this.reload(),
        });
    }

    async onStart() {
        if (await this.props.record.save()) {
            await this.reload();
        }
    }
}

registry.category("view_widgets").add("advanced_timesheet_grid", {
    component: TimesheetGrid,
});

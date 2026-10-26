import { Component, onWillStart, onWillUpdateProps, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { deserializeDate, formatDate, serializeDate } from "@web/core/l10n/dates";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { exprToBoolean } from "@web/core/utils/strings";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { standardViewProps } from "@web/views/standard_view_props";
import { getActiveActions } from "@web/views/utils";

const { DateTime } = luxon;

const ROW_HEIGHT = 36;
const LABEL_WIDTH = 280;
const SCALES = {
    day: { label: _t("Days"), pxPerDay: 36 },
    week: { label: _t("Weeks"), pxPerDay: 16 },
    month: { label: _t("Months"), pxPerDay: 5 },
};

/**
 * Reads the <project_gantt> arch: which fields hold the dates, the rows'
 * grouping, the task links (drawn as arrows), milestones, stage category
 * (bar colour) and assignees.
 */
export class GanttArchParser {
    parse(xmlDoc) {
        const attr = (name, fallback = false) => xmlDoc.getAttribute(name) || fallback;
        return {
            activeActions: getActiveActions(xmlDoc),
            dateStart: attr("date_start"),
            dateStop: attr("date_stop"),
            groupBy: attr("group_by"),
            linkField: attr("link_field"),
            milestoneField: attr("milestone_field"),
            stateField: attr("state_field"),
            assigneeField: attr("assignee_field"),
            defaultScale: SCALES[attr("default_scale")] ? attr("default_scale") : "week",
            editable: exprToBoolean(attr("edit", "1"), true),
        };
    }
}

/**
 * A Gantt chart of tasks: rows grouped (by phase), bars that can be dragged
 * to move or resized from either end, milestones as diamonds, and the links
 * between tasks as arrows. Drag from a bar's dot to another bar to link them
 * (the first becomes the parent). Click an unscheduled row to schedule it.
 */
export class GanttController extends Component {
    static template = "advanced_projects.GanttView";
    static components = { Layout, SearchBar, CogMenu };
    static props = { ...standardViewProps, archInfo: Object };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.rootRef = useRef("root");
        this.bodyRef = useRef("body");
        this.searchBarToggler = useSearchBarToggler();
        this.rowHeight = ROW_HEIGHT;
        this.labelWidth = LABEL_WIDTH;
        this.scales = SCALES;
        this.state = useState({
            loading: true,
            tasks: [],
            scale: this.props.archInfo.defaultScale,
            collapsed: {},
            drag: null,
            link: null,
        });
        onWillStart(() => this.load(this.props));
        onWillUpdateProps((nextProps) => this.load(nextProps));
    }

    get archInfo() {
        return this.props.archInfo;
    }

    get canEdit() {
        return this.archInfo.activeActions.edit && this.archInfo.editable;
    }

    get canCreate() {
        return this.archInfo.activeActions.create;
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------

    async load(props) {
        const a = this.archInfo;
        const fields = ["display_name", a.dateStart, a.dateStop, a.groupBy, a.linkField,
            a.milestoneField, a.stateField, a.assigneeField].filter(Boolean);
        const modelFields = props.fields;
        const order = [a.groupBy, "sequence" in modelFields ? "sequence" : false, a.dateStart, "id"]
            .filter(Boolean).join(", ");
        const records = await this.orm.searchRead(props.resModel, props.domain, [...new Set(fields)], {
            context: props.context,
            order,
        });
        this.state.tasks = records.map((rec) => ({
            id: rec.id,
            name: rec.display_name,
            start: rec[a.dateStart] ? deserializeDate(rec[a.dateStart]) : null,
            stop: rec[a.dateStop] ? deserializeDate(rec[a.dateStop]) : null,
            group: a.groupBy && rec[a.groupBy] ? rec[a.groupBy] : false,
            links: a.linkField ? rec[a.linkField] || [] : [],
            milestone: a.milestoneField ? Boolean(rec[a.milestoneField]) : false,
            category: a.stateField ? rec[a.stateField] || "todo" : "todo",
            assignees: a.assigneeField ? rec[a.assigneeField] || [] : [],
        }));
        this.state.loading = false;
    }

    async reload() {
        await this.load(this.props);
    }

    // ------------------------------------------------------------------
    // Layout: the visible date range and the rows
    // ------------------------------------------------------------------

    get pxPerDay() {
        return SCALES[this.state.scale].pxPerDay;
    }

    get range() {
        const dates = [];
        for (const task of this.state.tasks) {
            if (task.start) {
                dates.push(task.start);
            }
            if (task.stop) {
                dates.push(task.stop);
            }
        }
        const today = DateTime.local().startOf("day");
        dates.push(today);
        let start = DateTime.min(...dates).minus({ days: 7 });
        let stop = DateTime.max(...dates).plus({ days: 21 });
        if (this.state.scale === "month") {
            start = start.startOf("month");
            stop = stop.endOf("month").startOf("day");
        } else {
            start = start.startOf("week");
            stop = stop.endOf("week").startOf("day");
        }
        const minDays = Math.ceil(1400 / this.pxPerDay);
        if (stop.diff(start, "days").days < minDays) {
            stop = start.plus({ days: minDays });
        }
        return { start, stop, days: Math.round(stop.diff(start, "days").days) + 1 };
    }

    get timelineWidth() {
        return this.range.days * this.pxPerDay;
    }

    dayIndex(date) {
        return Math.round(date.startOf("day").diff(this.range.start, "days").days);
    }

    /** The header: months on top, then days or week starts. */
    get headerCells() {
        const { start, days } = this.range;
        const px = this.pxPerDay;
        const months = [];
        const units = [];
        let current = null;
        for (let i = 0; i < days; i++) {
            const date = start.plus({ days: i });
            const key = date.toFormat("yyyy-MM");
            if (!current || current.key !== key) {
                current = { key, label: date.toFormat("LLL yyyy"), left: i * px, width: 0 };
                months.push(current);
            }
            current.width += px;
            if (this.state.scale === "day") {
                units.push({ key: i, label: date.toFormat("d"), left: i * px, width: px,
                    weekend: date.weekday > 5, title: formatDate(date) });
            } else if (this.state.scale === "week" && date.weekday === 1) {
                units.push({ key: i, label: date.toFormat("dd/MM"), left: i * px, width: 7 * px,
                    weekend: false, title: formatDate(date) });
            }
        }
        return { months, units };
    }

    get weekends() {
        if (this.state.scale === "month") {
            return [];
        }
        const { start, days } = this.range;
        const result = [];
        for (let i = 0; i < days; i++) {
            if (start.plus({ days: i }).weekday === 6) {
                result.push({ key: i, left: i * this.pxPerDay, width: 2 * this.pxPerDay });
            }
        }
        return result;
    }

    get todayLeft() {
        return (this.dayIndex(DateTime.local()) + 0.5) * this.pxPerDay;
    }

    /** Group rows (with a summary bar) followed by their task rows. */
    get rows() {
        const rows = [];
        const groups = new Map();
        for (const task of this.state.tasks) {
            const key = task.group ? task.group[0] : 0;
            if (!groups.has(key)) {
                groups.set(key, {
                    key,
                    label: task.group ? task.group[1] : _t("No %s", this.groupLabel),
                    tasks: [],
                });
            }
            groups.get(key).tasks.push(task);
        }
        const useGroups = Boolean(this.archInfo.groupBy);
        for (const group of groups.values()) {
            if (useGroups) {
                const scheduled = group.tasks.filter((t) => t.start || t.stop);
                let bar = null;
                if (scheduled.length) {
                    const first = Math.min(...scheduled.map((t) => this.dayIndex(t.start || t.stop)));
                    const last = Math.max(...scheduled.map((t) => this.dayIndex(t.stop || t.start)));
                    bar = { left: first * this.pxPerDay, width: (last - first + 1) * this.pxPerDay };
                }
                const done = group.tasks.filter((t) => t.category === "done").length;
                const counted = group.tasks.filter((t) => t.category !== "cancelled").length;
                rows.push({
                    type: "group",
                    key: `g${group.key}`,
                    groupKey: group.key,
                    label: group.label,
                    count: group.tasks.length,
                    progress: counted ? Math.round((100 * done) / counted) : 0,
                    bar,
                    collapsed: Boolean(this.state.collapsed[group.key]),
                });
            }
            if (useGroups && this.state.collapsed[group.key]) {
                continue;
            }
            for (const task of group.tasks) {
                rows.push({ type: "task", key: `t${task.id}`, task, bar: this.barFor(task) });
            }
        }
        return rows;
    }

    get groupLabel() {
        const field = this.props.fields[this.archInfo.groupBy];
        return field ? field.string : _t("Group");
    }

    /** Position of a task's bar, including any drag in progress. */
    barFor(task) {
        if (!task.start && !task.stop) {
            return null;
        }
        let first = this.dayIndex(task.start || task.stop);
        let last = this.dayIndex(task.stop || task.start);
        const drag = this.state.drag;
        if (drag && drag.taskId === task.id) {
            if (drag.mode === "move") {
                first += drag.delta;
                last += drag.delta;
            } else if (drag.mode === "start") {
                first = Math.min(first + drag.delta, last);
            } else if (drag.mode === "stop") {
                last = Math.max(last + drag.delta, first);
            }
        }
        return {
            left: first * this.pxPerDay,
            width: (last - first + 1) * this.pxPerDay,
            first,
            last,
        };
    }

    rowTop(index) {
        return index * ROW_HEIGHT;
    }

    /** Arrows from each task to the tasks it links to (parent → child). */
    get linkPaths() {
        const rows = this.rows;
        const positions = {};
        rows.forEach((row, index) => {
            if (row.type === "task" && row.bar) {
                positions[row.task.id] = { ...row.bar, y: index * ROW_HEIGHT + ROW_HEIGHT / 2 };
            }
        });
        const paths = [];
        for (const row of rows) {
            if (row.type !== "task") {
                continue;
            }
            const from = positions[row.task.id];
            if (!from) {
                continue;
            }
            for (const childId of row.task.links) {
                const to = positions[childId];
                if (!to) {
                    continue;
                }
                const x1 = from.left + from.width;
                const y1 = from.y;
                const x2 = to.left;
                const y2 = to.y;
                let d;
                if (x2 - x1 >= 16) {
                    const mid = x1 + 8;
                    d = `M ${x1} ${y1} H ${mid} V ${y2} H ${x2 - 2}`;
                } else {
                    const turn = y2 > y1 ? ROW_HEIGHT / 2 : -ROW_HEIGHT / 2;
                    d = `M ${x1} ${y1} h 8 v ${turn} H ${x2 - 10} V ${y2} H ${x2 - 2}`;
                }
                paths.push({
                    key: `${row.task.id}-${childId}`,
                    d,
                    late: to.first <= from.last,
                });
            }
        }
        return paths;
    }

    formatRange(task) {
        if (!task.start && !task.stop) {
            return _t("Not scheduled");
        }
        const start = task.start ? formatDate(task.start) : "";
        const stop = task.stop ? formatDate(task.stop) : "";
        return start && stop && start !== stop ? `${start} – ${stop}` : start || stop;
    }

    // ------------------------------------------------------------------
    // Interactions
    // ------------------------------------------------------------------

    setScale(scale) {
        this.state.scale = scale;
    }

    toggleGroup(row) {
        this.state.collapsed[row.groupKey] = !this.state.collapsed[row.groupKey];
    }

    scrollToToday() {
        const body = this.bodyRef.el;
        if (body) {
            body.scrollLeft = Math.max(0, this.todayLeft - (body.clientWidth - LABEL_WIDTH) / 3);
        }
    }

    openTask(task) {
        this.props.selectRecord?.(task.id);
    }

    onCreate() {
        this.props.createRecord?.();
    }

    onBarPointerDown(ev, task, mode) {
        if (!this.canEdit || ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        const startX = ev.clientX;
        this.state.drag = { taskId: task.id, mode, delta: 0, moved: false };
        const onMove = (moveEv) => {
            const delta = Math.round((moveEv.clientX - startX) / this.pxPerDay);
            if (Math.abs(moveEv.clientX - startX) > 3) {
                this.state.drag.moved = true;
            }
            this.state.drag.delta = delta;
        };
        const onUp = async () => {
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onUp);
            const drag = this.state.drag;
            this.state.drag = null;
            if (!drag.moved) {
                this.openTask(task);
                return;
            }
            if (drag.delta) {
                await this.saveDates(task, drag.mode, drag.delta);
            }
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
    }

    async saveDates(task, mode, delta) {
        const a = this.archInfo;
        let start = task.start || task.stop;
        let stop = task.stop || task.start;
        if (mode === "move") {
            start = start.plus({ days: delta });
            stop = stop.plus({ days: delta });
        } else if (mode === "start") {
            start = DateTime.min(start.plus({ days: delta }), stop);
        } else {
            stop = DateTime.max(stop.plus({ days: delta }), start);
        }
        await this.write(task.id, { [a.dateStart]: serializeDate(start), [a.dateStop]: serializeDate(stop) });
    }

    async write(resId, values) {
        try {
            await this.orm.write(this.props.resModel, [resId], values, { context: this.props.context });
        } finally {
            await this.reload();
        }
    }

    /** Schedule an unscheduled task on the day clicked in its row. */
    async onRowClick(ev, row) {
        if (row.type !== "task" || row.bar || !this.canEdit) {
            return;
        }
        const rect = ev.currentTarget.getBoundingClientRect();
        const index = Math.floor((ev.clientX - rect.left) / this.pxPerDay);
        const date = serializeDate(this.range.start.plus({ days: index }));
        const a = this.archInfo;
        await this.write(row.task.id, { [a.dateStart]: date, [a.dateStop]: date });
    }

    /** Drag from a bar's dot onto another bar: the first becomes its parent. */
    onLinkPointerDown(ev, task) {
        if (!this.canEdit || !this.archInfo.linkField || ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        const body = this.bodyRef.el.querySelector(".o_adv_gantt_rows");
        const rect = body.getBoundingClientRect();
        const point = (e) => ({ x: e.clientX - rect.left - LABEL_WIDTH, y: e.clientY - rect.top });
        const origin = point(ev);
        this.state.link = { fromId: task.id, x1: origin.x, y1: origin.y, x2: origin.x, y2: origin.y };
        const onMove = (moveEv) => {
            const p = point(moveEv);
            this.state.link.x2 = p.x;
            this.state.link.y2 = p.y;
        };
        const onUp = async (upEv) => {
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onUp);
            this.state.link = null;
            const target = document.elementFromPoint(upEv.clientX, upEv.clientY)?.closest("[data-task-id]");
            const childId = target ? parseInt(target.dataset.taskId) : null;
            if (!childId || childId === task.id) {
                return;
            }
            try {
                await this.orm.write(this.props.resModel, [task.id], {
                    [this.archInfo.linkField]: [[4, childId]],
                }, { context: this.props.context });
                this.notification.add(_t("Tasks linked."), { type: "success" });
            } finally {
                await this.reload();
            }
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
    }

    onLinkClick(path) {
        if (!this.canEdit) {
            return;
        }
        const [parentId, childId] = path.key.split("-").map((id) => parseInt(id));
        const names = Object.fromEntries(this.state.tasks.map((t) => [t.id, t.name]));
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove Link"),
            body: _t("Unlink “%(child)s” from its parent “%(parent)s”?", {
                child: names[childId],
                parent: names[parentId],
            }),
            confirmLabel: _t("Remove Link"),
            confirm: () => this.write(parentId, { [this.archInfo.linkField]: [[3, childId]] }),
            cancel: () => {},
        });
    }
}

export const ganttView = {
    type: "project_gantt",
    display_name: _t("Gantt"),
    icon: "fa fa-align-left",
    multiRecord: true,
    searchMenuTypes: ["filter", "favorite"],
    ArchParser: GanttArchParser,
    Controller: GanttController,
    props: (genericProps, view) => ({
        ...genericProps,
        archInfo: new view.ArchParser().parse(genericProps.arch),
    }),
};

registry.category("views").add("project_gantt", ganttView);

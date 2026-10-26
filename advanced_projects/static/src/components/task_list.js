import { Component } from "@odoo/owl";

/**
 * A compact table of tasks (from a task filter): used by the Overview's task
 * widgets and the task widgets of Project Updates.
 */
export class TaskList extends Component {
    static template = "advanced_projects.TaskList";
    static props = {
        rows: Array,
        total: { type: Number, optional: true },
        taskFilter: { type: String, optional: true },
        showAssignees: { type: Boolean, optional: true },
        showDates: { type: Boolean, optional: true },
        showPhase: { type: Boolean, optional: true },
        showStage: { type: Boolean, optional: true },
        onOpen: { type: Function, optional: true },
    };
    static defaultProps = {
        showAssignees: true,
        showDates: true,
        showPhase: true,
        showStage: true,
    };

    get more() {
        return Math.max(0, (this.props.total || 0) - this.props.rows.length);
    }

    dates(row) {
        if (this.props.taskFilter === "completed" && row.date_done) {
            return row.date_done;
        }
        if (row.date_start && row.date_end && row.date_start !== row.date_end) {
            return `${row.date_start} – ${row.date_end}`;
        }
        return row.date_end || row.date_start;
    }
}

import { Component, markup, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { TaskList } from "../components/task_list";

const WIDTH_CLASSES = {
    small: "col-12 col-lg-4",
    medium: "col-12 col-lg-6",
    large: "col-12 col-lg-8",
    full: "col-12",
};
const WIDTH_ORDER = ["small", "medium", "large", "full"];

/**
 * A project's Overview: a header with the project's key facts and links to
 * its Tasks, Gantt chart, Updates and Team, then a grid of widgets. In
 * Customize mode widgets are added from a palette (click or drag), dragged
 * into place, resized, configured and removed; the layout is saved per
 * project.
 */
export class ProjectOverview extends Component {
    static template = "advanced_projects.ProjectOverview";
    static components = { Layout, TaskList };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.widthClasses = WIDTH_CLASSES;
        this.display = { controlPanel: {} };
        this.projectId =
            this.props.action.params?.project_id || this.props.action.context?.active_id || false;
        this.state = useState({
            data: null,
            editing: false,
            dragging: null,
            dropIndex: null,
        });
        onWillStart(() => this.load());
    }

    async load() {
        if (!this.projectId) {
            return;
        }
        this.state.data = await this.orm.call("advanced.project", "get_overview_data", [[this.projectId]]);
    }

    get project() {
        return this.state.data?.project;
    }

    get widgets() {
        return this.state.data?.widgets || [];
    }

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------

    async openProjectAction(method, args = []) {
        const action = await this.orm.call("advanced.project", method, [[this.projectId], ...args]);
        await this.action.doAction(action);
    }

    openTasks(viewType = "kanban") {
        return this.openProjectAction("action_open_tasks", [viewType]);
    }

    openFilteredTasks(taskFilter, days = 14) {
        return this.openProjectAction("action_open_tasks_filtered", [taskFilter, days]);
    }

    openRecord(resModel, resId) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: resModel,
            res_id: resId,
            views: [[false, "form"]],
        });
    }

    async invite() {
        const action = await this.orm.call("advanced.project", "action_invite", [[this.projectId]]);
        await this.action.doAction(action, { onClose: () => this.load() });
    }

    // ------------------------------------------------------------------
    // Customize
    // ------------------------------------------------------------------

    toggleEditing() {
        this.state.editing = !this.state.editing;
    }

    async addWidget(item, index = null) {
        const widgetId = await this.orm.call("advanced.project", "overview_add_widget", [
            [this.projectId],
            item.type,
            item.task_filter || false,
        ]);
        await this.load();
        if (index !== null) {
            const ids = this.widgets.map((w) => w.id).filter((id) => id !== widgetId);
            ids.splice(index, 0, widgetId);
            await this.saveOrder(ids);
        }
    }

    async saveOrder(ids) {
        await this.orm.call("advanced.project", "overview_resequence", [[this.projectId], ids]);
        await this.load();
    }

    async cycleWidth(widget) {
        const next = WIDTH_ORDER[(WIDTH_ORDER.indexOf(widget.width) + 1) % WIDTH_ORDER.length];
        await this.orm.write("advanced.project.overview.widget", [widget.id], { width: next });
        widget.width = next;
    }

    configure(widget) {
        this.dialog.add(FormViewDialog, {
            resModel: "advanced.project.overview.widget",
            resId: widget.id,
            title: _t("Configure “%s”", widget.title),
            onRecordSaved: () => this.refreshWidget(widget.id),
        });
    }

    async refreshWidget(widgetId) {
        const [values] = await this.orm.call("advanced.project.overview.widget", "get_widget_values", [[widgetId]]);
        const index = this.state.data.widgets.findIndex((w) => w.id === widgetId);
        if (index >= 0 && values) {
            this.state.data.widgets[index] = values;
        }
    }

    remove(widget) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove Widget"),
            body: _t("Remove “%s” from the Overview?", widget.title),
            confirmLabel: _t("Remove"),
            confirm: async () => {
                await this.orm.unlink("advanced.project.overview.widget", [widget.id]);
                await this.load();
            },
            cancel: () => {},
        });
    }

    resetLayout() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Reset Overview"),
            body: _t("Replace this Overview's widgets with the default layout?"),
            confirmLabel: _t("Reset"),
            confirm: async () => {
                await this.orm.call("advanced.project", "overview_reset", [[this.projectId]]);
                await this.load();
            },
            cancel: () => {},
        });
    }

    // Drag and drop: palette items and widgets share the same drop targets.
    onPaletteDragStart(ev, item) {
        ev.dataTransfer.effectAllowed = "copy";
        ev.dataTransfer.setData("text/plain", item.label);
        this.state.dragging = { kind: "palette", item };
    }

    onWidgetDragStart(ev, widget) {
        if (!this.state.editing) {
            ev.preventDefault();
            return;
        }
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", widget.title);
        this.state.dragging = { kind: "widget", widgetId: widget.id };
    }

    onDragEnd() {
        this.state.dragging = null;
        this.state.dropIndex = null;
    }

    onWidgetDragOver(ev, index) {
        if (!this.state.dragging) {
            return;
        }
        ev.preventDefault();
        const rect = ev.currentTarget.getBoundingClientRect();
        const after = ev.clientX > rect.left + rect.width / 2;
        this.state.dropIndex = after ? index + 1 : index;
    }

    onGridDragOver(ev) {
        if (!this.state.dragging) {
            return;
        }
        ev.preventDefault();
        // between widgets keep the current drop place; below the last one, drop at the end
        const widgets = ev.currentTarget.querySelectorAll(".o_adv_widget");
        const last = widgets[widgets.length - 1];
        if (!last || ev.clientY > last.getBoundingClientRect().bottom) {
            this.state.dropIndex = this.widgets.length;
        }
    }

    async onDrop(ev) {
        ev.preventDefault();
        const dragging = this.state.dragging;
        const index = this.state.dropIndex ?? this.widgets.length;
        this.onDragEnd();
        if (!dragging) {
            return;
        }
        if (dragging.kind === "palette") {
            await this.addWidget(dragging.item, index);
            return;
        }
        const ids = this.widgets.map((w) => w.id);
        const from = ids.indexOf(dragging.widgetId);
        ids.splice(from, 1);
        ids.splice(from < index ? index - 1 : index, 0, dragging.widgetId);
        await this.saveOrder(ids);
    }

    // ------------------------------------------------------------------
    // Helpers for the templates
    // ------------------------------------------------------------------

    asHtml(html) {
        // sanitized by the server (Html field)
        return markup(html);
    }

    daysLeftLabel(days) {
        if (days === null || days === undefined) {
            return "";
        }
        if (days < 0) {
            return _t("%s days overdue", -days);
        }
        if (days === 0) {
            return _t("Due today");
        }
        return _t("%s days left", days);
    }
}

registry.category("actions").add("advanced_project_overview", ProjectOverview);

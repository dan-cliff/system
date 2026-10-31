import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

/**
 * Warehouse layout designer: draw a warehouse's rooms, aisles and shelves on
 * its floor plan (in metres) and list every tote. Each item is a real
 * stock.location (stock.warehouse.layout_designer_save), so products,
 * labels, signs and the Scanner app all use them. "Number Walk Order"
 * numbers the route through the warehouse that picking and put-away follow.
 */

const LEVEL_ORDER = ["room", "aisle", "shelf", "tote"];
const LEVEL_ICONS = { room: "fa-square-o", aisle: "fa-columns", shelf: "fa-bars", tote: "fa-archive" };
const SNAP = 0.1;
const SWATCHES = ["#F2F2FA", "#A9ABDC", "#3BB8FF", "#0A6CF0", "#14C9A5", "#14A3A3",
    "#8E5CF0", "#5B3DB8", "#FFC93C", "#FF9F1C", "#F9A3A3", "#FF5A6E"];

function round(value, step = SNAP) {
    return Math.round(Math.round(value / step) * step * 100) / 100;
}

let newId = 0;
function tempId() {
    newId += 1;
    return `new_${Date.now().toString(36)}_${newId}`;
}

export class LayoutDesigner extends Component {
    static template = "advanced_inventory.LayoutDesigner";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.levelIcons = LEVEL_ICONS;
        this.swatches = SWATCHES;
        const params = this.props.action.params || {};
        this.warehouseId = params.warehouse_id || this.props.action.context?.active_id;
        this.state = useState({
            loading: true,
            warehouse: {},
            levels: [],
            nodes: [],
            deleted: [],
            selectedId: params.select_location_id || false,
            collapsed: {},
            zoom: 20,
            dirty: false,
            saving: false,
            showPath: true,
            search: "",
        });
        this.drag = null;
        this.onPointerMove = this.onPointerMove.bind(this);
        this.onPointerUp = this.onPointerUp.bind(this);
        this.onBeforeUnload = (ev) => {
            if (this.state.dirty) {
                ev.preventDefault();
                ev.returnValue = "";
            }
        };
        window.addEventListener("beforeunload", this.onBeforeUnload);
        onWillStart(() => this.load());
        onWillUnmount(() => {
            this.stopDrag();
            window.removeEventListener("beforeunload", this.onBeforeUnload);
        });
    }

    // ── Loading and saving ──────────────────────────────────────────────

    async load() {
        const data = await this.orm.call("stock.warehouse", "layout_designer_load", [this.warehouseId || false]);
        this.warehouseId = data.warehouse.id;
        this.apply(data);
        this.fit();
    }

    apply(data) {
        this.state.warehouse = data.warehouse;
        this.state.levels = data.levels;
        this.state.nodes = data.nodes;
        this.state.deleted = [];
        this.state.dirty = false;
        this.state.loading = false;
        if (this.state.selectedId && !this.nodeById(this.state.selectedId)) {
            this.state.selectedId = false;
        }
    }

    payload() {
        return this.state.nodes.map((n) => ({
            id: n.id, parent_id: n.parent_id || false, name: n.name, level: n.level, code: n.code,
            barcode: n.barcode, x: n.x, y: n.y, w: n.w, h: n.h, color: n.color, sequence: n.sequence,
        }));
    }

    async save(numberWalk = false) {
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const selected = this.selected;
            const data = await this.orm.call("stock.warehouse", "layout_designer_save", [
                this.warehouseId, this.payload(), this.state.deleted, numberWalk,
            ]);
            this.apply(data);
            if (selected && typeof selected.id === "string") {
                // Find the new location again by its place in the layout.
                const match = this.state.nodes.find((n) => n.name === selected.name && n.level === selected.level &&
                    Math.abs(n.x - selected.x) < 0.01 && Math.abs(n.y - selected.y) < 0.01);
                this.state.selectedId = match ? match.id : false;
            }
            this.notification.add(numberWalk ? _t("Layout saved and walk order numbered.") : _t("Layout saved."),
                { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }

    async numberWalk() {
        if (this.state.dirty) {
            await this.save(true);
            return;
        }
        this.state.saving = true;
        try {
            this.apply(await this.orm.call("stock.warehouse", "layout_designer_number_walk", [this.warehouseId]));
            this.notification.add(_t("Walk order numbered: picking and put-away now follow it."), { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }

    discard() {
        if (!this.state.dirty) {
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Discard Changes"),
            body: _t("Undo every change since the layout was last saved?"),
            confirmLabel: _t("Discard"),
            confirm: () => this.load(),
            cancel: () => {},
        });
    }

    touch() {
        this.state.dirty = true;
    }

    // ── Tree ────────────────────────────────────────────────────────────

    isSaved(node) {
        return Boolean(node) && typeof node.id === "number";
    }

    nodeById(id) {
        return this.state.nodes.find((n) => n.id === id);
    }

    get selected() {
        return this.nodeById(this.state.selectedId) || false;
    }

    childrenOf(parentId) {
        return this.state.nodes
            .filter((n) => (n.parent_id || false) === (parentId || false))
            .sort((a, b) => (a.walk || 1e9) - (b.walk || 1e9) || a.sequence - b.sequence ||
                String(a.name).localeCompare(String(b.name)));
    }

    descendants(id) {
        const result = [];
        const walk = (parentId) => {
            for (const child of this.state.nodes.filter((n) => n.parent_id === parentId)) {
                result.push(child);
                walk(child.id);
            }
        };
        walk(id);
        return result;
    }

    ancestorOfLevel(node, level) {
        let current = node;
        while (current) {
            if (current.level === level) {
                return current;
            }
            current = current.parent_id ? this.nodeById(current.parent_id) : null;
        }
        return null;
    }

    matchesSearch(node) {
        const term = this.state.search.trim().toLowerCase();
        if (!term) {
            return true;
        }
        const own = `${node.name} ${node.code} ${node.barcode}`.toLowerCase().includes(term);
        return own || this.descendants(node.id).some((d) => `${d.name} ${d.code} ${d.barcode}`.toLowerCase().includes(term));
    }

    toggleCollapse(node, ev) {
        ev.stopPropagation();
        this.state.collapsed[node.id] = !this.state.collapsed[node.id];
    }

    levelLabel(level) {
        const found = this.state.levels.find((l) => l.key === level);
        return found ? found.label : level;
    }

    get counts() {
        const counts = {};
        for (const level of LEVEL_ORDER) {
            counts[level] = this.state.nodes.filter((n) => n.level === level).length;
        }
        return counts;
    }

    // ── Adding ──────────────────────────────────────────────────────────

    /** The parent a new location of this level goes in, given the selection. */
    parentFor(level) {
        const sel = this.selected;
        if (level === "room") {
            return { ok: true, parent: null };
        }
        if (level === "aisle") {
            return { ok: true, parent: sel ? this.ancestorOfLevel(sel, "room") : null };
        }
        const needed = level === "shelf" ? "aisle" : "shelf";
        const parent = sel ? this.ancestorOfLevel(sel, needed) : null;
        return { ok: Boolean(parent), parent };
    }

    canAdd(level) {
        return this.parentFor(level).ok;
    }

    addTitle(level) {
        if (this.canAdd(level)) {
            return _t("Add a %s", this.levelLabel(level).toLowerCase());
        }
        return level === "shelf" ? _t("Select an aisle first: shelves go in aisles.")
            : _t("Select a shelf first: totes go on shelves.");
    }

    addNode(level) {
        const { ok, parent } = this.parentFor(level);
        if (!ok) {
            this.notification.add(this.addTitle(level), { type: "warning" });
            return;
        }
        const spec = this.state.levels.find((l) => l.key === level);
        const siblings = this.state.nodes.filter((n) => n.level === level && (n.parent_id || false) === (parent ? parent.id : false));
        const number = siblings.length + 1;
        let [w, h] = spec.size;
        let x = 1, y = 1;
        if (parent && level !== "tote") {
            const vertical = parent.h >= parent.w;
            if (level === "shelf") {
                // Shelves line up along their aisle.
                if (vertical) {
                    w = Math.min(parent.w, w);
                    h = Math.min(h, parent.h);
                    x = parent.x;
                    y = parent.y + Math.min(siblings.length * h, Math.max(parent.h - h, 0));
                } else {
                    [w, h] = [h, Math.min(parent.h, w)];
                    x = parent.x + Math.min(siblings.length * w, Math.max(parent.w - w, 0));
                    y = parent.y;
                }
            } else {
                // Aisles side by side in their room, with a walkway between.
                w = Math.min(w, parent.w);
                h = Math.min(h, Math.max(parent.h - 2, 1));
                x = parent.x + 1 + Math.min(siblings.length * (w + 2.5), Math.max(parent.w - w - 1, 0));
                y = parent.y + 1;
            }
        } else if (!parent) {
            const top = this.state.nodes.filter((n) => !n.parent_id);
            x = 1 + (top.length % 4) * (w + 2);
            y = 1 + Math.floor(top.length / 4) * (h + 2);
            if (level === "aisle") {
                h = Math.min(h, this.state.warehouse.floor_depth - 2);
            }
        }
        const node = {
            id: tempId(),
            parent_id: parent ? parent.id : false,
            name: `${this.levelLabel(level)} ${number}`,
            level,
            code: `${parent && level !== "room" && parent.code ? parent.code + "-" : ""}${spec.prefix}${number}`,
            barcode: "",
            x: round(x), y: round(y), w: round(w), h: round(h),
            color: "",
            sequence: (siblings.length + 1) * 10,
            walk: 0,
            contents: [],
            slots: [],
        };
        if (level === "tote" && parent) {
            Object.assign(node, { x: parent.x, y: parent.y, w: spec.size[0], h: spec.size[1] });
        }
        this.state.nodes.push(node);
        if (parent) {
            this.state.collapsed[parent.id] = false;
        }
        this.state.selectedId = node.id;
        this.touch();
    }

    removeSelected() {
        const node = this.selected;
        if (!node) {
            return;
        }
        const all = [node, ...this.descendants(node.id)];
        const stocked = all.find((n) => n.contents && n.contents.length);
        if (stocked) {
            this.notification.add(_t("%s still holds stock. Move the stock before removing it from the layout.", stocked.name),
                { type: "warning" });
            return;
        }
        const remove = () => {
            const ids = new Set(all.map((n) => n.id));
            this.state.deleted.push(...all.filter((n) => typeof n.id === "number").map((n) => n.id));
            this.state.nodes = this.state.nodes.filter((n) => !ids.has(n.id));
            this.state.selectedId = node.parent_id || false;
            this.touch();
        };
        if (all.length > 1) {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Remove %s", node.name),
                body: _t("This also removes the %s locations inside it.", all.length - 1),
                confirmLabel: _t("Remove"),
                confirm: remove,
                cancel: () => {},
            });
        } else {
            remove();
        }
    }

    duplicateSelected() {
        const node = this.selected;
        if (!node || node.level === "room") {
            return;
        }
        const offset = node.h >= node.w ? [node.w + 1, 0] : [0, node.h + 1];
        const copy = { ...node, id: tempId(), name: `${node.name} (copy)`, code: node.code ? `${node.code}B` : "",
            barcode: "", walk: 0, contents: [], slots: [],
            x: round(node.x + offset[0]), y: round(node.y + offset[1]) };
        this.state.nodes.push(copy);
        // Copy what is inside too (shelves of an aisle, totes of a shelf).
        const map = { [node.id]: copy.id };
        for (const child of this.descendants(node.id)) {
            const childCopy = { ...child, id: tempId(), parent_id: map[child.parent_id], barcode: "", walk: 0,
                contents: [], slots: [], code: child.code ? `${child.code}B` : "",
                x: round(child.x + offset[0]), y: round(child.y + offset[1]) };
            map[child.id] = childCopy.id;
            this.state.nodes.push(childCopy);
        }
        this.state.selectedId = copy.id;
        this.touch();
    }

    // ── Properties ──────────────────────────────────────────────────────

    setProp(name, value) {
        const node = this.selected;
        if (!node) {
            return;
        }
        node[name] = value;
        this.touch();
    }

    setNumber(name, ev, min = -10000) {
        const value = parseFloat(ev.target.value);
        if (Number.isNaN(value)) {
            return;
        }
        const node = this.selected;
        const clean = round(Math.max(value, min), 0.01);
        if (name === "x" || name === "y") {
            this.moveBy(node, name === "x" ? clean - node.x : 0, name === "y" ? clean - node.y : 0);
        } else {
            node[name] = Math.max(clean, 0.05);
        }
        this.touch();
    }

    rotateSelected() {
        const node = this.selected;
        if (!node) {
            return;
        }
        [node.w, node.h] = [node.h, node.w];
        this.touch();
    }

    validParents(node) {
        if (!node || node.level === "room") {
            return [];
        }
        const rank = LEVEL_ORDER.indexOf(node.level);
        const own = new Set([node.id, ...this.descendants(node.id).map((d) => d.id)]);
        return this.state.nodes.filter((n) => !own.has(n.id) && LEVEL_ORDER.indexOf(n.level) < rank &&
            (node.level !== "shelf" || n.level === "aisle") && (node.level !== "tote" || n.level === "shelf"));
    }

    canBeTopLevel(node) {
        return node && (node.level === "room" || node.level === "aisle");
    }

    onParentChange(ev) {
        const value = ev.target.value;
        this.setProp("parent_id", value === "" ? false : (/^\d+$/.test(value) ? parseInt(value) : value));
    }

    moveTote(step) {
        const node = this.selected;
        if (!node || node.level !== "tote") {
            return;
        }
        const siblings = this.state.nodes.filter((n) => n.level === "tote" && n.parent_id === node.parent_id)
            .sort((a, b) => a.sequence - b.sequence);
        const index = siblings.indexOf(node);
        const other = siblings[index + step];
        if (!other) {
            return;
        }
        siblings.forEach((s, i) => { s.sequence = (i + 1) * 10; });
        [node.sequence, other.sequence] = [other.sequence, node.sequence];
        this.touch();
    }

    async openLocation() {
        const node = this.selected;
        if (!node || typeof node.id !== "number") {
            return;
        }
        if (this.state.dirty) {
            await this.save();
        }
        await this.action.doAction({
            type: "ir.actions.act_window", res_model: "stock.location", res_id: node.id,
            views: [[false, "form"]], target: "current",
        });
    }

    async printLabel() {
        const node = this.selected;
        if (!node || typeof node.id !== "number") {
            this.notification.add(_t("Save the layout first to print its labels."), { type: "warning" });
            return;
        }
        const action = await this.orm.call("stock.location", "action_print_layout_label", [[node.id]]);
        await this.action.doAction(action);
    }

    async printLevelLabels(level) {
        if (this.state.dirty) {
            await this.save();
        }
        const ids = this.state.nodes.filter((n) => n.level === level && typeof n.id === "number")
            .sort((a, b) => (a.walk || 0) - (b.walk || 0)).map((n) => n.id);
        if (!ids.length) {
            return;
        }
        const action = await this.orm.call("stock.location", "action_print_layout_label", [ids]);
        await this.action.doAction(action);
    }

    // ── Floor plan ──────────────────────────────────────────────────────

    fit() {
        const width = this.state.warehouse.floor_width || 40;
        const depth = this.state.warehouse.floor_depth || 25;
        const available = Math.max(window.innerWidth - 640, 480);
        this.state.zoom = Math.max(Math.min(Math.floor(Math.min(available / width, 620 / depth)), 120), 4);
    }

    zoomBy(factor) {
        this.state.zoom = Math.max(Math.min(Math.round(this.state.zoom * factor), 200), 2);
    }

    async setFloor(name, ev) {
        const value = parseFloat(ev.target.value);
        if (Number.isNaN(value) || value < 1 || value > 2000) {
            return;
        }
        await this.orm.write("stock.warehouse", [this.warehouseId],
            { [name === "floor_width" ? "layout_floor_width" : "layout_floor_depth"]: value });
        this.state.warehouse[name] = value;
    }

    get floorStyle() {
        const z = this.state.zoom;
        return `width:${this.state.warehouse.floor_width * z}px;height:${this.state.warehouse.floor_depth * z}px;` +
            `background-size:${z}px ${z}px, ${z * 5}px ${z * 5}px`;
    }

    get drawn() {
        // Big things first so smaller ones sit on top.
        return this.state.nodes.filter((n) => n.level !== "tote")
            .sort((a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level));
    }

    totesOf(node) {
        return this.state.nodes.filter((n) => n.level === "tote" && n.parent_id === node.id)
            .sort((a, b) => a.sequence - b.sequence);
    }

    nodeColor(node) {
        if (node.color) {
            return node.color;
        }
        const spec = this.state.levels.find((l) => l.key === node.level);
        return spec ? spec.color : "#A9ABDC";
    }

    nodeStyle(node) {
        const z = this.state.zoom;
        return [
            `left:${node.x * z}px`, `top:${node.y * z}px`,
            `width:${Math.max(node.w * z, 4)}px`, `height:${Math.max(node.h * z, 4)}px`,
            `--node-color:${this.nodeColor(node)}`,
        ].join(";");
    }

    nodeClass(node) {
        const classes = [`o_ild_node o_ild_${node.level}`];
        if (node.id === this.state.selectedId) {
            classes.push("o_ild_selected");
        }
        const sel = this.selected;
        if (sel && sel.level === "tote" && sel.parent_id === node.id) {
            classes.push("o_ild_selected_parent");
        }
        if (node.contents && node.contents.length) {
            classes.push("o_ild_stocked");
        }
        if (!this.matchesSearch(node)) {
            classes.push("o_ild_dimmed");
        }
        return classes.join(" ");
    }

    showLabel(node) {
        return node.w * this.state.zoom > 26 && node.h * this.state.zoom > 14;
    }

    /** The walk through the shelves (or aisles without shelves), for the path overlay. */
    get walkPoints() {
        const z = this.state.zoom;
        const stops = this.state.nodes.filter((n) => n.walk > 0 && (n.level === "shelf" ||
            (n.level === "aisle" && !this.state.nodes.some((c) => c.parent_id === n.id))))
            .sort((a, b) => a.walk - b.walk);
        return stops.map((n, index) => ({
            id: n.id, index: index + 1, x: (n.x + n.w / 2) * z, y: (n.y + n.h / 2) * z,
        }));
    }

    get walkPolyline() {
        return this.walkPoints.map((p) => `${p.x},${p.y}`).join(" ");
    }

    get walkStale() {
        return this.state.nodes.some((n) => !n.walk) || this.state.dirty;
    }

    // ── Dragging ────────────────────────────────────────────────────────

    select(node) {
        this.state.selectedId = node ? node.id : false;
    }

    moveBy(node, dx, dy) {
        for (const n of [node, ...this.descendants(node.id)]) {
            n.x = round(n.x + dx, 0.01);
            n.y = round(n.y + dy, 0.01);
        }
    }

    onNodePointerDown(ev, node, handle = false) {
        if (ev.button !== 0) {
            return;
        }
        ev.stopPropagation();
        ev.preventDefault();
        this.select(node);
        this.drag = {
            node, handle, startX: ev.clientX, startY: ev.clientY,
            orig: { x: node.x, y: node.y, w: node.w, h: node.h }, moved: false,
            children: this.descendants(node.id).map((c) => ({ c, x: c.x, y: c.y })),
        };
        window.addEventListener("pointermove", this.onPointerMove);
        window.addEventListener("pointerup", this.onPointerUp);
    }

    onPointerMove(ev) {
        const drag = this.drag;
        if (!drag) {
            return;
        }
        const step = ev.altKey ? 0.01 : SNAP;
        const dx = (ev.clientX - drag.startX) / this.state.zoom;
        const dy = (ev.clientY - drag.startY) / this.state.zoom;
        const node = drag.node;
        drag.moved = true;
        if (!drag.handle) {
            node.x = round(drag.orig.x + dx, step);
            node.y = round(drag.orig.y + dy, step);
            const realDx = node.x - drag.orig.x;
            const realDy = node.y - drag.orig.y;
            for (const item of drag.children) {
                item.c.x = round(item.x + realDx, 0.01);
                item.c.y = round(item.y + realDy, 0.01);
            }
            return;
        }
        if (drag.handle.includes("e")) {
            node.w = Math.max(round(drag.orig.w + dx, step), 0.1);
        }
        if (drag.handle.includes("s")) {
            node.h = Math.max(round(drag.orig.h + dy, step), 0.1);
        }
    }

    onPointerUp() {
        const moved = this.drag && this.drag.moved;
        this.stopDrag();
        if (moved) {
            this.touch();
        }
    }

    stopDrag() {
        this.drag = null;
        window.removeEventListener("pointermove", this.onPointerMove);
        window.removeEventListener("pointerup", this.onPointerUp);
    }

    onKeydown(ev) {
        const node = this.selected;
        if (!node || ["INPUT", "TEXTAREA", "SELECT"].includes(ev.target.tagName)) {
            return;
        }
        const step = ev.shiftKey ? 1 : SNAP;
        const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
        if (moves[ev.key] && node.level !== "tote") {
            ev.preventDefault();
            this.moveBy(node, ...moves[ev.key]);
            this.touch();
        } else if (ev.key === "Delete") {
            ev.preventDefault();
            this.removeSelected();
        } else if (ev.key === "d" && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            this.duplicateSelected();
        } else if (ev.key === "Escape") {
            this.select(false);
        } else if (ev.key === "s" && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            this.save();
        }
    }

    async leave() {
        try {
            await this.action.restore();
        } catch {
            // Opened directly (no previous screen): go to the warehouse list.
            await this.action.doAction("advanced_inventory.action_warehouse_layout", { clearBreadcrumbs: true });
        }
    }

    back() {
        if (!this.state.dirty) {
            this.leave();
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Unsaved Changes"),
            body: _t("Leave the designer without saving the layout?"),
            confirmLabel: _t("Leave"),
            confirm: () => {
                this.state.dirty = false;
                this.leave();
            },
            cancel: () => {},
        });
    }
}

registry.category("actions").add("advanced_inventory.layout_designer", LayoutDesigner);

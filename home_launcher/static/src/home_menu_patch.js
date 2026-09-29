import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { HomeMenu } from "@web_enterprise/webclient/home_menu/home_menu";
import { ToolboxPopup } from "./toolbox_popup";
import { onWillStart, useState } from "@odoo/owl";

// Render our grouped launcher template and expose the folder popup component.
HomeMenu.template = "home_launcher.HomeMenu";
HomeMenu.components = { ...HomeMenu.components, ToolboxPopup };

let tempIdSeq = -1;

patch(HomeMenu.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.launcher = useState({
            layoutLoaded: false,
            source: "none", // "user" | "global" | "none"
            toolboxes: [], // [{id, name, icon, color, sequence, appIds: [menuId, ...]}]
            openFolderId: null,
            editMode: false,
        });
        this._draggedAppId = null;

        onWillStart(async () => {
            await this._loadLayout();
        });
    },

    //--------------------------------------------------------------------------
    // Data loading
    //--------------------------------------------------------------------------

    async _loadLayout() {
        const layout = await this.orm.call("home.toolbox", "get_home_layout", []);
        this.launcher.source = layout.source;
        this.launcher.toolboxes = (layout.toolboxes || []).map((tb) => ({
            id: tb.id,
            name: tb.name,
            icon: tb.icon || "fa-folder",
            color: tb.color || "#714B67",
            sequence: tb.sequence,
            appIds: (tb.apps || []).map((a) => a.menu_id),
        }));
        this.launcher.layoutLoaded = true;
    },

    //--------------------------------------------------------------------------
    // Getters
    //--------------------------------------------------------------------------

    /**
     * Number of tiles per row, kept in sync with the 5-column CSS grid so
     * keyboard navigation wraps correctly.
     * @override
     */
    get maxIconNumber() {
        const w = window.innerWidth;
        if (w < 576) {
            return 3;
        } else if (w < 768) {
            return 4;
        }
        return 5;
    },

    /**
     * The tiles to render: folders (by sequence) first, then any app not placed
     * in a folder. Apps the current user cannot access are silently dropped
     * because they are absent from props.apps.
     * @returns {Object[]} [{type:'folder', toolbox, apps} | {type:'app', app}]
     */
    get tiles() {
        const apps = this.props.apps;
        const appById = new Map(apps.map((a) => [a.id, a]));
        const usedIds = new Set();
        const folders = [];
        const sorted = [...this.launcher.toolboxes].sort((a, b) => a.sequence - b.sequence);
        for (const tb of sorted) {
            const folderApps = [];
            for (const menuId of tb.appIds) {
                const app = appById.get(menuId);
                if (app && !usedIds.has(app.id)) {
                    folderApps.push(app);
                    usedIds.add(app.id);
                }
            }
            // Hide empty folders in normal mode; keep them visible while editing.
            if (folderApps.length || this.launcher.editMode) {
                folders.push({ type: "folder", toolbox: tb, apps: folderApps });
            }
        }
        const loose = apps
            .filter((a) => !usedIds.has(a.id))
            .map((a) => ({ type: "app", app: a }));
        return [...folders, ...loose];
    },

    get openFolder() {
        if (this.launcher.openFolderId == null) {
            return null;
        }
        return (
            this.tiles.find(
                (t) => t.type === "folder" && t.toolbox.id === this.launcher.openFolderId
            ) || null
        );
    },

    //--------------------------------------------------------------------------
    // View-mode interactions
    //--------------------------------------------------------------------------

    _onTileClick(tile) {
        if (this.launcher.editMode) {
            return;
        }
        if (tile.type === "folder") {
            this.launcher.openFolderId = tile.toolbox.id;
        } else {
            this._openMenu(tile.app);
        }
    },

    closeFolder() {
        this.launcher.openFolderId = null;
    },

    //--------------------------------------------------------------------------
    // Edit mode
    //--------------------------------------------------------------------------

    toggleEditMode() {
        this.launcher.editMode = !this.launcher.editMode;
        this.launcher.openFolderId = null;
    },

    async cancelEdit() {
        this.launcher.editMode = false;
        await this._loadLayout();
    },

    createFolder() {
        const name = window.prompt(_t("Toolbox name"), _t("New toolbox"));
        if (!name) {
            return;
        }
        const maxSeq = this.launcher.toolboxes.reduce((m, t) => Math.max(m, t.sequence), 0);
        this.launcher.toolboxes.push({
            id: tempIdSeq--,
            name,
            icon: "fa-folder",
            color: "#714B67",
            sequence: maxSeq + 10,
            appIds: [],
        });
    },

    renameFolder(toolbox) {
        const name = window.prompt(_t("Rename toolbox"), toolbox.name);
        if (name) {
            toolbox.name = name;
        }
    },

    deleteFolder(toolbox) {
        // Apps inside become loose automatically once the folder is removed.
        const idx = this.launcher.toolboxes.findIndex((t) => t.id === toolbox.id);
        if (idx !== -1) {
            this.launcher.toolboxes.splice(idx, 1);
        }
    },

    _moveAppToFolder(appId, folderId) {
        // Remove from every folder first.
        for (const tb of this.launcher.toolboxes) {
            const i = tb.appIds.indexOf(appId);
            if (i !== -1) {
                tb.appIds.splice(i, 1);
            }
        }
        // Then add to the target folder (folderId null => keep loose).
        if (folderId != null) {
            const target = this.launcher.toolboxes.find((t) => t.id === folderId);
            if (target && !target.appIds.includes(appId)) {
                target.appIds.push(appId);
            }
        }
    },

    async saveLayout() {
        const payload = [...this.launcher.toolboxes]
            .sort((a, b) => a.sequence - b.sequence)
            .map((tb, index) => ({
                name: tb.name,
                icon: tb.icon,
                color: tb.color,
                sequence: (index + 1) * 10,
                app_menu_ids: tb.appIds,
            }));
        await this.orm.call("home.toolbox", "set_home_layout", [payload]);
        this.launcher.editMode = false;
        await this._loadLayout();
        this.notification.add(_t("Home layout saved."), { type: "success" });
    },

    async resetLayout() {
        await this.orm.call("home.toolbox", "reset_my_layout", []);
        this.launcher.editMode = false;
        await this._loadLayout();
        this.notification.add(_t("Reset to the default layout."), { type: "info" });
    },

    //--------------------------------------------------------------------------
    // Drag & drop (edit mode)
    //--------------------------------------------------------------------------

    onAppDragStart(ev, app) {
        if (!this.launcher.editMode) {
            return;
        }
        this._draggedAppId = app.id;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(app.id));
    },

    onFolderDragOver(ev) {
        if (this.launcher.editMode && this._draggedAppId != null) {
            ev.preventDefault();
        }
    },

    onFolderDrop(ev, toolbox) {
        if (!this.launcher.editMode || this._draggedAppId == null) {
            return;
        }
        ev.preventDefault();
        this._moveAppToFolder(this._draggedAppId, toolbox.id);
        this._draggedAppId = null;
    },

    onLooseDragOver(ev) {
        if (this.launcher.editMode && this._draggedAppId != null) {
            ev.preventDefault();
        }
    },

    onLooseDrop(ev) {
        if (!this.launcher.editMode || this._draggedAppId == null) {
            return;
        }
        ev.preventDefault();
        this._moveAppToFolder(this._draggedAppId, null);
        this._draggedAppId = null;
    },
});

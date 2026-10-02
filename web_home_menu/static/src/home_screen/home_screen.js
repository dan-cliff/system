import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Component, useState, onMounted, onWillStart, onWillUnmount } from "@odoo/owl";
import { FolderPopup } from "../folder_popup/folder_popup";

const DEFAULT_FOLDER_COLOR = "#714B67";
let tempFolderId = -1;

export class HomeScreen extends Component {
    static template = "web_home_menu.HomeScreen";
    static components = { FolderPopup };
    static props = ["*"];

    setup() {
        this.menuService = useService("menu");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.ui = useService("ui");
        this.state = useState({ searchTerm: "" });
        this.layout = useState({
            source: "none", // "user" | "default" | "none"
            canEditDefault: false,
            // [{id, name, icon, color, appIds: [menuId, ...]}], in display order
            folders: [],
            openFolderId: null,
            editMode: false,
        });
        this.draggedAppId = null;
        onWillStart(() => this.loadLayout());
        // Let the navbar know the home screen is showing, so it can hide its
        // own menus/waffle button and only keep a few systray icons visible.
        onMounted(() => this.env.bus.trigger("HOME_MENU:VISIBILITY", { isVisible: true }));
        onWillUnmount(() => this.env.bus.trigger("HOME_MENU:VISIBILITY", { isVisible: false }));
    }

    async loadLayout() {
        const layout = await this.orm.call("home.menu.folder", "get_home_layout", []);
        this.layout.source = layout.source;
        this.layout.canEditDefault = layout.can_edit_default;
        this.layout.folders = layout.folders.map((folder) => ({
            id: folder.id,
            name: folder.name,
            icon: folder.icon,
            color: folder.color,
            appIds: folder.app_menu_ids,
        }));
        this.layout.openFolderId = null;
    }

    //--------------------------------------------------------------------------
    // Getters
    //--------------------------------------------------------------------------

    get apps() {
        // getApps() already returns apps in ir.ui.menu sequence order; keep
        // that order instead of re-sorting alphabetically so the home
        // screen matches the menu model's ordering.
        return this.menuService.getApps();
    }

    get isSearching() {
        return Boolean(this.state.searchTerm.trim());
    }

    /**
     * Apps matching the search term. While searching, the home screen shows
     * these as a flat list so apps inside folders can still be found.
     */
    get searchResults() {
        const term = this.state.searchTerm.trim().toLowerCase();
        return this.apps.filter((app) => app.name.toLowerCase().includes(term));
    }

    /**
     * Folders first, then every app not placed in a folder. Apps the user
     * can't access aren't in getApps(), so they silently drop out of folders.
     * @returns {Object[]} [{type: "folder", folder, apps} | {type: "app", app}]
     */
    get tiles() {
        const appById = new Map(this.apps.map((app) => [app.id, app]));
        const usedIds = new Set();
        const tiles = [];
        for (const folder of this.layout.folders) {
            const apps = [];
            for (const menuId of folder.appIds) {
                const app = appById.get(menuId);
                if (app && !usedIds.has(app.id)) {
                    apps.push(app);
                    usedIds.add(app.id);
                }
            }
            // Empty folders only show while editing, so they can be filled.
            if (apps.length || this.layout.editMode) {
                tiles.push({ type: "folder", folder, apps });
            }
        }
        for (const app of this.apps) {
            if (!usedIds.has(app.id)) {
                tiles.push({ type: "app", app });
            }
        }
        return tiles;
    }

    get openFolderTile() {
        return (
            this.tiles.find(
                (tile) => tile.type === "folder" && tile.folder.id === this.layout.openFolderId
            ) || null
        );
    }

    get canEditLayout() {
        return !this.ui.isSmall && !this.isSearching;
    }

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    onSearchInput(ev) {
        this.state.searchTerm = ev.target.value;
    }

    openApp(app) {
        if (this.layout.editMode) {
            return;
        }
        this.menuService.selectMenu(app);
    }

    openFolder(folder) {
        this.layout.openFolderId = folder.id;
    }

    closeFolder() {
        this.layout.openFolderId = null;
    }

    //--------------------------------------------------------------------------
    // Edit mode
    //--------------------------------------------------------------------------

    startEdit() {
        this.layout.editMode = true;
        this.layout.openFolderId = null;
    }

    async cancelEdit() {
        this.layout.editMode = false;
        await this.loadLayout();
    }

    createFolder() {
        this.layout.folders.push({
            id: tempFolderId--,
            name: _t("New folder"),
            icon: "fa-folder",
            color: DEFAULT_FOLDER_COLOR,
            appIds: [],
        });
    }

    renameFolder(folder, ev) {
        folder.name = ev.target.value.trim() || folder.name;
    }

    recolorFolder(folder, ev) {
        folder.color = ev.target.value;
    }

    deleteFolder(folder) {
        // Its apps go back to the main grid once the folder is gone.
        this.layout.folders = this.layout.folders.filter((f) => f.id !== folder.id);
        if (this.layout.openFolderId === folder.id) {
            this.layout.openFolderId = null;
        }
    }

    moveFolder(folder, offset) {
        const folders = this.layout.folders;
        const index = folders.findIndex((f) => f.id === folder.id);
        const target = index + offset;
        if (index === -1 || target < 0 || target >= folders.length) {
            return;
        }
        [folders[index], folders[target]] = [folders[target], folders[index]];
    }

    /**
     * Take an app out of whatever folder holds it, then put it in the target
     * folder (or leave it loose on the grid when folderId is null).
     */
    moveAppToFolder(appId, folderId) {
        for (const folder of this.layout.folders) {
            folder.appIds = folder.appIds.filter((id) => id !== appId);
        }
        if (folderId !== null) {
            const target = this.layout.folders.find((f) => f.id === folderId);
            if (target) {
                target.appIds.push(appId);
            }
        }
    }

    async saveLayout(scope = "user") {
        const folders = this.layout.folders.map((folder) => ({
            name: folder.name,
            icon: folder.icon,
            color: folder.color,
            app_menu_ids: folder.appIds,
        }));
        await this.orm.call("home.menu.folder", "set_home_layout", [folders, scope]);
        this.layout.editMode = false;
        await this.loadLayout();
        this.notification.add(
            scope === "default"
                ? _t("Default home screen layout saved for everyone.")
                : _t("Your home screen layout has been saved."),
            { type: "success" }
        );
    }

    async resetLayout() {
        await this.orm.call("home.menu.folder", "reset_my_layout", []);
        this.layout.editMode = false;
        await this.loadLayout();
        this.notification.add(_t("Your home screen is back to the default layout."), {
            type: "info",
        });
    }

    //--------------------------------------------------------------------------
    // Drag & drop (edit mode)
    //--------------------------------------------------------------------------

    onAppDragStart(ev, app) {
        if (!this.layout.editMode) {
            ev.preventDefault();
            return;
        }
        this.draggedAppId = app.id;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(app.id));
    }

    onAppDragEnd() {
        this.draggedAppId = null;
    }

    onDragOver(ev) {
        if (this.layout.editMode && this.draggedAppId !== null) {
            ev.preventDefault();
        }
    }

    onFolderDrop(ev, folder) {
        if (!this.layout.editMode || this.draggedAppId === null) {
            return;
        }
        ev.preventDefault();
        this.moveAppToFolder(this.draggedAppId, folder.id);
        this.draggedAppId = null;
    }

    onGridDrop(ev) {
        if (!this.layout.editMode || this.draggedAppId === null) {
            return;
        }
        ev.preventDefault();
        this.moveAppToFolder(this.draggedAppId, null);
        this.draggedAppId = null;
    }
}

const actionRegistry = registry.category("actions");
actionRegistry.add("web_home_menu.home_screen", HomeScreen);
// "menu" is the tag the web client treats as the home menu: the router leaves
// it out of the URL (so it shows as plain /odoo) and it is never listed in
// breadcrumbs. Community doesn't register it; Enterprise's own home menu does.
if (!actionRegistry.contains("menu")) {
    actionRegistry.add("menu", HomeScreen);
}

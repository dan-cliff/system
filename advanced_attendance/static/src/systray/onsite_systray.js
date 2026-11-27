import { Component, onWillStart, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { useDropdownState } from "@web/core/dropdown/dropdown_hooks";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { ConnectionLostError, rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * On Site: sign in / sign out button in the top toolbar.
 * Shown for employees with the "Attendances: Sign In from Odoo" permission
 * when the company allows signing in from Odoo.
 */
export class OnSiteSystray extends Component {
    static components = { Dropdown };
    static props = [];
    static template = "advanced_attendance.OnSiteSystray";

    setup() {
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.dropdown = useDropdownState();
        this.formatHours = registry.category("formatters").get("float_time");
        this.state = useState({ employee: false, busy: false });
        onWillStart(() => {
            // Don't hold up the web client while this loads.
            this.load();
        });
    }

    async load() {
        const employee = await rpc("/advanced_attendance/systray_data", {}, { silent: true });
        this.state.employee = employee && employee.id ? employee : false;
    }

    get signedIn() {
        return this.state.employee && this.state.employee.state === "checked_in";
    }

    get hoursToday() {
        return this.formatHours(this.state.employee.hours_today || 0);
    }

    get since() {
        const last = this.state.employee.last_check_in;
        return last ? deserializeDateTime(last).toFormat("HH:mm") : "";
    }

    async send(latitude = false, longitude = false) {
        try {
            const employee = await rpc("/advanced_attendance/systray_sign_in_out", { latitude, longitude });
            this.state.employee = employee && employee.id ? employee : false;
            if (this.state.employee) {
                this.notification.add(this.signedIn ? _t("You are signed in.") : _t("You are signed out."), {
                    type: "success",
                });
            }
        } catch (error) {
            if (error instanceof ConnectionLostError) {
                this.notification.add(_t("Connection lost. Your sign in or out was not recorded."), {
                    title: _t("On Site"),
                    type: "danger",
                });
            } else {
                throw error;
            }
        } finally {
            this.state.busy = false;
        }
    }

    signInOut() {
        this.dropdown.close();
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        if (!this.state.employee.location_tracking) {
            return this.send();
        }
        const askWithoutLocation = () =>
            this.dialog.add(ConfirmationDialog, {
                body: _t("Your location could not be found. Sign in or out without it?"),
                confirmLabel: _t("Continue"),
                confirm: () => this.send(),
                cancel: () => {
                    this.state.busy = false;
                },
            });
        if (!navigator.geolocation || !navigator.onLine) {
            return askWithoutLocation();
        }
        navigator.geolocation.getCurrentPosition(
            ({ coords }) => this.send(coords.latitude, coords.longitude),
            askWithoutLocation,
            { enableHighAccuracy: true, timeout: 10000 }
        );
    }
}

registry.category("systray").add(
    "advanced_attendance.onsite_systray",
    { Component: OnSiteSystray, showOnHomeScreen: true },
    { sequence: 101 }
);

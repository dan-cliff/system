import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * GeoLocation answer: a latitude field (this widget) and its longitude
 * field, filled from the device's location or typed in, with a map link.
 */
export class ChecklistGeolocationField extends Component {
    static template = "checklists.GeolocationField";
    static props = { ...standardFieldProps, longitudeField: { type: String, optional: true } };
    static defaultProps = { longitudeField: "value_longitude" };

    setup() {
        this.notification = useService("notification");
        this.state = useState({ locating: false });
    }

    get latitude() {
        return this.props.record.data[this.props.name] || 0;
    }

    get longitude() {
        return this.props.record.data[this.props.longitudeField] || 0;
    }

    get isSet() {
        return Boolean(this.latitude || this.longitude);
    }

    get display() {
        return `${this.latitude.toFixed(6)}, ${this.longitude.toFixed(6)}`;
    }

    get mapUrl() {
        return `https://www.openstreetmap.org/?mlat=${this.latitude}&mlon=${this.longitude}#map=17/${this.latitude}/${this.longitude}`;
    }

    update(latitude, longitude) {
        this.props.record.update({
            [this.props.name]: latitude,
            [this.props.longitudeField]: longitude,
        });
    }

    onInput(ev, which) {
        const value = parseFloat(ev.target.value);
        if (which === "latitude") {
            this.update(isNaN(value) ? 0 : value, this.longitude);
        } else {
            this.update(this.latitude, isNaN(value) ? 0 : value);
        }
    }

    locate() {
        if (!navigator.geolocation) {
            this.notification.add(_t("This device can't share its location."), { type: "warning" });
            return;
        }
        this.state.locating = true;
        navigator.geolocation.getCurrentPosition(
            (position) => {
                this.state.locating = false;
                this.update(position.coords.latitude, position.coords.longitude);
            },
            (error) => {
                this.state.locating = false;
                this.notification.add(_t("Couldn't get the location: %s", error.message), {
                    type: "warning",
                });
            },
            { enableHighAccuracy: true, timeout: 20000 }
        );
    }

    clear() {
        this.update(0, 0);
    }
}

registry.category("fields").add("checklist_geolocation", {
    component: ChecklistGeolocationField,
    displayName: _t("GeoLocation"),
    supportedTypes: ["float"],
    isEmpty: () => false,
    extractProps: ({ options }) => ({ longitudeField: options.longitude_field }),
});

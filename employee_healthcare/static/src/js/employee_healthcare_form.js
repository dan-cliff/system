/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/**
 * Patch the FormController to intercept saves on employee.healthcare records.
 *
 * When the user saves a dirty (modified) healthcare record, a confirmation
 * dialog is shown asking them to verify the profile is accurate:
 *
 *  • "Confirm"         → save + stamp last_verified with current datetime + navigate back
 *  • "Save and Go Back"→ save normally + stay on the record (last_verified unchanged)
 */
patch(FormController.prototype, {
    setup() {
        super.setup();
        // Store services so they are accessible in async save callbacks.
        this._healthcareOrm = useService("orm");
        this._healthcareNotification = useService("notification");
    },

    async save(params = {}) {
        // Only intercept the employee.healthcare form — leave all other forms alone.
        if (this.model.root.resModel !== "employee.healthcare") {
            return super.save(params);
        }

        // If there are no unsaved changes, skip the dialog and return immediately.
        const isDirty = await this.model.root.isDirty();
        if (!isDirty) {
            return super.save(params);
        }

        // Capture a reference to the parent save so it can be called from
        // within arrow-function callbacks (arrow fns inherit [[HomeObject]]
        // from this method, so the super keyword is valid here).
        const doSave = (p) => super.save(p);

        return new Promise((resolve) => {
            this.dialogService.add(ConfirmationDialog, {
                title: _t("Verify Care Profile"),
                body: _t(
                    "By clicking Confirm, I confirm that this care profile is " +
                    "up-to-date and accurate to the best of my knowledge."
                ),
                confirmLabel: _t("Confirm"),
                cancelLabel: _t("Save and Go Back"),

                // "Confirm": save → stamp last_verified → navigate back.
                confirm: async () => {
                    const saved = await doSave(params);
                    if (saved) {
                        await this._healthcareOrm.call(
                            "employee.healthcare",
                            "action_confirm_verified",
                            [[this.model.root.resId]],
                        );
                        this.env.config.historyBack();
                        this._healthcareNotification.add(
                            _t("Employee Care Profile confirmed and updated."),
                            { type: "success" }
                        );
                    }
                    resolve(saved);
                },

                // "Save and Go Back": save only — last_verified is NOT updated.
                // The dialog closes and the user remains on the record.
                cancel: async () => {
                    const saved = await doSave(params);
                    resolve(saved);
                },
            });
        });
    },
});

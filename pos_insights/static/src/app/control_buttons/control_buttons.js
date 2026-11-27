import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";
import { downloadReport } from "@web/webclient/actions/reports/utils";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";

patch(ControlButtons.prototype, {
    /**
     * The logged-in cashier: the Odoo user, or with employee login (pos_hr)
     * the employee, whose linked user's permission is checked by
     * pos_insights_hr.
     */
    get posInsightsCashier() {
        return this.pos.getCashier();
    },

    get showPosInsights() {
        return Boolean(this.posInsightsCashier?._pos_insights);
    },

    async clickPosInsightsReports() {
        // Close the Actions popup first so the report picker isn't stacked on it.
        this.props.close?.();
        const reportCode = await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("Reports - %s", this.pos.session.name),
            list: [
                { id: 1, label: _t("Orders"), item: "orders" },
                { id: 2, label: _t("Sales Details"), item: "sales_details" },
                { id: 3, label: _t("Session Report"), item: "session" },
            ],
        });
        if (!reportCode) {
            return;
        }
        const cashier = this.posInsightsCashier;
        const employeeId = cashier?.model?.name === "hr.employee" ? cashier.id : false;
        this.ui.block();
        try {
            const action = await this.pos.data.call(
                "pos.session",
                "get_pos_insights_report_action",
                [[this.pos.session.id], reportCode, employeeId]
            );
            const { success, message } = await downloadReport(rpc, action, "pdf", user.context);
            if (!success) {
                this.dialog.add(AlertDialog, {
                    title: _t("Report could not be printed"),
                    body: message,
                });
            }
        } catch (error) {
            this.dialog.add(AlertDialog, {
                title: _t("Report could not be printed"),
                body:
                    error?.data?.message ||
                    _t("Check your connection to the server and try again."),
            });
        } finally {
            this.ui.unblock();
        }
    },
});

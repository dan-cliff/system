/** @odoo-module */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PosBagPopup } from "@pos_bag_charges/js/PosBagPopupWidget";
import { _t } from "@web/core/l10n/translation";

patch(PosStore.prototype, {
    async onclick_bag() {
        const order = this.getOrder();
        const categoryId = this.config.raw.bag_category_id;

        if (!categoryId) {
            return this.notification.add(
                _t("Bag category not configured!"),
                { type: "danger" }
            );
        }
        const products = this.data.models["product.template"].getBy("pos_categ_ids",categoryId);

        if (!products || products.length === 0) {
            return this.notification.add(
                _t("Currently no Bag Products available!"),
                { type: "danger" }
            );
        }

        if (products.length === 1) {
            const tpl = products[0];

            this.addLineToCurrentOrder({
                product_tmpl_id: tpl,
                product_id: tpl.product_variant_ids[0],
                tax_ids: tpl.taxes_id.map(t => ["link", t]),
            });

            this.navigate("ProductScreen", {
                orderUuid: order?.uuid,
            });
            return;
        }

        products.forEach((p) => {
            p.image_url = `/web/binary/image?model=product.template&field=image_medium&id=${p.id}`;
        });

        await makeAwaitable(this.dialog, PosBagPopup, { products });
    },
});

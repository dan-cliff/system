/** @odoo-module */

import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";

export class PosBagPopup extends Component {
    static template = "pos_bag_charges.PosBagPopup";
    static components = { Dialog };

    setup() {
        this.pos = usePos();
    }

    get bags() {
        const bags = [];
        this.props.products.forEach(prd => {
            prd['bag_image_url'] = `/web/image?model=product.template&field=image_128&id=${prd.id}&write_date=${prd.write_date}&unique=1`;
            bags.push(prd);
        });
        return bags;
    }
    
    click_on_bag_product(event) {
        const bag_id = parseInt(event.currentTarget.dataset.productId);

        const productTemplate = this.pos.data.models["product.template"].get(bag_id);

        if (!productTemplate) {
            return;
        }

        this.pos.addLineToCurrentOrder({
            product_tmpl_id: productTemplate,
            product_id: productTemplate.product_variant_ids[0],
        });

        this.pos.navigate('ProductScreen', {
            orderUuid: this.pos.getOrder().uuid,
        });

        this.props.close();
    }

}
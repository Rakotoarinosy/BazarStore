"""Conversion commande (modèle SQLAlchemy) → réponse HTTP, partagée par les routes et les flux SSE."""

from src.features.order.schemas import OrderOut
from src.infrastructure.persistence.models import OrderModel


def serialize_order(order: OrderModel) -> OrderOut:
    """OrderOut avec, pour les anciennes lignes sans image, l'image actuelle du produit."""
    output = OrderOut.model_validate(order)
    products_by_id = {
        item.product_id: item.product
        for item in order.items
        if item.product_id is not None and item.product is not None
    }
    for item_output in output.items:
        product = products_by_id.get(item_output.product_id)
        if item_output.product_image_url is None and product is not None:
            item_output.product_image_url = (
                f"/api/v1/products/images/{product.image_key}"
                if product.image_key
                else product.image_url
            )
    return output

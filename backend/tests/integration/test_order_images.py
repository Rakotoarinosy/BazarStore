from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.domain.user import User
from src.features.order.router import create_order, list_my_orders
from src.features.order.schemas import OrderCreateIn, OrderItemCreateIn
from src.infrastructure.persistence.models import (
    OrderItemModel,
    OrderModel,
    ProductCategoryModel,
    ProductModel,
    UserModel,
)


def test_order_images_support_storage_keys_and_legacy_items(db_session: Session) -> None:
    user_id = "customer-1"
    user_model = UserModel(id=user_id, email="customer@example.com", name="Customer")
    category = ProductCategoryModel(id="category-1", name="Accessories", slug="accessories")
    product = ProductModel(
        id="product-1",
        code="PRODUCT-1",
        name="Product",
        price=1000,
        quantity=5,
        category=category,
        image_key="products/product-image.webp",
    )
    old_order = OrderModel(
        id="order-1",
        reference="CMD-OLD",
        user_id=user_id,
        customer_name=user_model.name,
        customer_email=user_model.email,
        status="pending",
        total_amount=1000,
        items=[
            OrderItemModel(
                id="item-1",
                product=product,
                product_name=product.name,
                product_image_url=None,
                unit_price=1000,
                quantity=1,
                line_total=1000,
            )
        ],
    )
    db_session.add_all([user_model, product, old_order])
    db_session.commit()

    user = User(
        id=user_id,
        email=user_model.email,
        name=user_model.name,
        created_at=datetime.now(UTC),
        password_hash="",
    )
    image_url = "/api/v1/products/images/products/product-image.webp"

    old_orders = list_my_orders(db_session, user)
    assert old_orders[0].items[0].product_image_url == image_url

    new_order = create_order(
        OrderCreateIn(items=[OrderItemCreateIn(product_id=product.id, quantity=1)]),
        db_session,
        user,
    )
    assert new_order.items[0].product_image_url == image_url

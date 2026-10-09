"""Création et consultation des commandes liées à l'utilisateur connecté."""

import secrets

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from src.domain.errors import DomainError
from src.domain.user import User
from src.features.order.schemas import OrderCreateIn, OrderOut
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.models import (
    OrderItemModel,
    OrderModel,
    ProductCategoryModel,
    ProductModel,
)
from src.infrastructure.security.deps import get_current_user

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderProductConflictError(DomainError):
    def __init__(self, product_id: str) -> None:
        super().__init__(f"Le produit {product_id} n'est plus disponible ou le stock est insuffisant.")


class OrderConflictError(DomainError):
    def __init__(self) -> None:
        super().__init__("La commande n'a pas pu être enregistrée. Veuillez réessayer.")


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OrderOut:
    requested = {item.product_id: item.quantity for item in payload.items}
    products = db.scalars(
        select(ProductModel)
        .join(ProductCategoryModel)
        .where(
            ProductModel.id.in_(requested),
            ProductModel.is_active.is_(True),
            ProductCategoryModel.is_active.is_(True),
        )
        .order_by(ProductModel.id)
        .with_for_update()
    ).all()
    products_by_id = {product.id: product for product in products}

    for product_id, quantity in requested.items():
        product = products_by_id.get(product_id)
        if product is None or product.quantity < quantity:
            raise OrderProductConflictError(product_id)

    lines = [
        OrderItemModel(
            product_id=product.id,
            product_name=product.name,
            product_image_url=product.image_url,
            unit_price=product.price,
            quantity=requested[product.id],
            line_total=product.price * requested[product.id],
        )
        for product in products
    ]
    order = OrderModel(
        reference=f"CMD-{secrets.token_hex(5).upper()}",
        user_id=user.id,
        customer_name=user.name,
        customer_email=user.email,
        status="pending",
        total_amount=sum(line.line_total for line in lines),
        items=lines,
    )
    db.add(order)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise OrderConflictError() from exc
    db.refresh(order)
    return OrderOut.model_validate(order)


@router.get("/mine", response_model=list[OrderOut])
def list_my_orders(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[OrderOut]:
    orders = db.scalars(
        select(OrderModel)
        .options(selectinload(OrderModel.items))
        .where(OrderModel.user_id == user.id)
        .order_by(OrderModel.created_at.desc())
    )
    return [OrderOut.model_validate(order) for order in orders]

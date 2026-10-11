"""Favoris anonymes de la boutique et classement de popularité pour le backoffice."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.errors import DomainError
from src.domain.user import Role
from src.features.reaction.schemas import PopularProduct, PopularProductsOut
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.models import (
    ProductCategoryModel,
    ProductModel,
    ProductReactionModel,
    utc_now,
)
from src.infrastructure.security.deps import require_roles

router = APIRouter(prefix="/reactions", tags=["reactions"])


class InvalidVisitorIdError(DomainError):
    def __init__(self) -> None:
        super().__init__("Identifiant visiteur invalide.")


class ReactionProductNotFoundError(DomainError):
    def __init__(self) -> None:
        super().__init__("Ce produit n'est pas disponible.")


def _visitor_hash(visitor_id: str) -> str:
    try:
        normalized = str(UUID(visitor_id))
    except (ValueError, AttributeError) as exc:
        raise InvalidVisitorIdError() from exc
    return hashlib.sha256(normalized.encode("ascii")).hexdigest()


def _require_active_product(db: Session, product_id: str) -> None:
    product = db.scalar(
        select(ProductModel.id)
        .join(ProductCategoryModel)
        .where(
            ProductModel.id == product_id,
            ProductModel.is_active.is_(True),
            ProductCategoryModel.is_active.is_(True),
        )
    )
    if product is None:
        raise ReactionProductNotFoundError()


@router.get("/mine", response_model=list[str])
def list_my_reactions(
    visitor_id: str = Header(alias="X-Visitor-Id"),
    db: Session = Depends(get_db),
) -> list[str]:
    """Retourne les produits favoris de ce navigateur anonyme."""
    visitor_hash = _visitor_hash(visitor_id)
    return list(
        db.scalars(
            select(ProductReactionModel.product_id).where(
                ProductReactionModel.visitor_hash == visitor_hash,
                ProductReactionModel.is_active.is_(True),
            )
        )
    )


@router.put(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def add_reaction(
    product_id: str,
    visitor_id: str = Header(alias="X-Visitor-Id"),
    db: Session = Depends(get_db),
) -> Response:
    """Ajoute le favori sans créer de doublon pour ce visiteur et ce produit."""
    _require_active_product(db, product_id)
    visitor_hash = _visitor_hash(visitor_id)
    reaction = db.get(ProductReactionModel, (product_id, visitor_hash))
    if reaction is None:
        now = utc_now()
        db.add(
            ProductReactionModel(
                product_id=product_id,
                visitor_hash=visitor_hash,
                first_reacted_at=now,
                last_reacted_at=now,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            # Deux clics simultanés peuvent tenter la même insertion ; PUT reste idempotent.
            db.rollback()
            if db.get(ProductReactionModel, (product_id, visitor_hash)) is None:
                raise
    elif not reaction.is_active:
        reaction.is_active = True
        reaction.last_reacted_at = utc_now()
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove_reaction(
    product_id: str,
    visitor_id: str = Header(alias="X-Visitor-Id"),
    db: Session = Depends(get_db),
) -> Response:
    """Retire le favori actif, tout en conservant une trace anonymisée."""
    visitor_hash = _visitor_hash(visitor_id)
    reaction = db.get(ProductReactionModel, (product_id, visitor_hash))
    if reaction is not None and reaction.is_active:
        reaction.is_active = False
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/popular",
    response_model=PopularProductsOut,
    dependencies=[Depends(require_roles(Role.COMMERCIAL))],
)
def popular_products(
    days: int = Query(default=30, ge=7, le=365),
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> PopularProductsOut:
    """Classe les produits d'après les navigateurs distincts qui les ont aimés."""
    since = datetime.now(UTC) - timedelta(days=days)
    active_count = func.coalesce(
        func.sum(case((ProductReactionModel.is_active.is_(True), 1), else_=0)), 0
    )
    recent_count = func.coalesce(
        func.sum(case((ProductReactionModel.last_reacted_at >= since, 1), else_=0)), 0
    )
    rows = db.execute(
        select(
            ProductModel.id,
            ProductModel.name,
            ProductModel.image_key,
            ProductModel.image_url,
            ProductCategoryModel.name.label("category"),
            func.count(ProductReactionModel.visitor_hash).label("visitors_total"),
            active_count.label("active_favorites"),
            recent_count.label("recent_reactions"),
        )
        .join(ProductCategoryModel)
        .outerjoin(ProductReactionModel, ProductReactionModel.product_id == ProductModel.id)
        .where(
            ProductModel.is_active.is_(True),
            ProductCategoryModel.is_active.is_(True),
            ProductReactionModel.visitor_hash.is_not(None),
        )
        .group_by(
            ProductModel.id,
            ProductModel.name,
            ProductModel.image_key,
            ProductModel.image_url,
            ProductCategoryModel.name,
        )
        .order_by(func.count(ProductReactionModel.visitor_hash).desc(), ProductModel.name)
        .limit(limit)
    ).all()

    products = [
        PopularProduct(
            product_id=row.id,
            name=row.name,
            category=row.category,
            image_url=(
                f"/api/v1/products/images/{row.image_key}" if row.image_key else row.image_url
            ),
            visitors_total=row.visitors_total,
            active_favorites=row.active_favorites,
            recent_reactions=row.recent_reactions,
        )
        for row in rows
    ]
    return PopularProductsOut(period_days=days, products=products)

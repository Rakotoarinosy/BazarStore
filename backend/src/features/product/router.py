"""Lecture publique des produits et CRUD du catalogue réservé aux administrateurs."""

import logging

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from src.domain.errors import DomainError
from src.domain.user import Role
from src.features.product.schemas import (
    ProductCreateIn,
    ProductImageUploadOut,
    ProductOut,
    ProductUpdateIn,
)
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.models import ProductCategoryModel, ProductModel
from src.infrastructure.security.deps import require_roles
from src.infrastructure.storage.minio_product_images import (
    MAX_PRODUCT_IMAGE_BYTES,
    InvalidProductImageError,
    MinioProductImageStorage,
)

router = APIRouter(prefix="/products", tags=["products"])
logger = logging.getLogger(__name__)


class ProductNotFoundError(DomainError):
    def __init__(self, product_id: str) -> None:
        super().__init__(f"Product '{product_id}' not found")


class ProductCategoryNotFoundError(DomainError):
    def __init__(self, category_id: str) -> None:
        super().__init__(f"Category '{category_id}' not found")


class ProductConflictError(DomainError):
    def __init__(self) -> None:
        super().__init__("Product code already exists or the category is still in use")


def _out(product: ProductModel) -> ProductOut:
    quantity = product.quantity
    inventory_status = "OUTOFSTOCK" if quantity == 0 else "LOWSTOCK" if quantity <= 5 else "INSTOCK"
    image_url = f"/api/v1/products/images/{product.image_key}" if product.image_key else product.image_url
    return ProductOut(
        id=product.id,
        code=product.code,
        name=product.name,
        description=product.description,
        price=product.price,
        quantity=quantity,
        inventory_status=inventory_status,
        image_url=image_url,
        image_key=product.image_key,
        category_id=product.category_id,
        category_name=product.category.name,
        is_active=product.is_active,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _validate_image_key(image_key: str | None) -> None:
    if image_key is not None and (not image_key.startswith("products/") or ".." in image_key):
        raise InvalidProductImageError("Invalid product image key")


def _delete_image_best_effort(image_key: str | None) -> None:
    if not image_key:
        return
    try:
        MinioProductImageStorage().delete(image_key)
    except Exception:
        logger.warning("Unable to remove product image from object storage", extra={"image_key": image_key})


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ProductConflictError() from exc


@router.get("", response_model=list[ProductOut])
def list_active_products(db: Session = Depends(get_db)) -> list[ProductOut]:
    products = db.scalars(
        select(ProductModel)
        .join(ProductCategoryModel)
        .options(joinedload(ProductModel.category))
        .where(ProductModel.is_active.is_(True), ProductCategoryModel.is_active.is_(True))
        .order_by(ProductModel.name)
    )
    return [_out(product) for product in products]


@router.get("/manage", response_model=list[ProductOut], dependencies=[Depends(require_roles(Role.ADMIN))])
def list_products_for_admin(db: Session = Depends(get_db)) -> list[ProductOut]:
    products = db.scalars(
        select(ProductModel).options(joinedload(ProductModel.category)).order_by(ProductModel.name)
    )
    return [_out(product) for product in products]


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles(Role.ADMIN))])
def create_product(payload: ProductCreateIn, db: Session = Depends(get_db)) -> ProductOut:
    if db.get(ProductCategoryModel, payload.category_id) is None:
        raise ProductCategoryNotFoundError(payload.category_id)
    _validate_image_key(payload.image_key)
    product = ProductModel(**payload.model_dump())
    db.add(product)
    _commit(db)
    db.refresh(product)
    return _out(product)


@router.patch("/{product_id}", response_model=ProductOut, dependencies=[Depends(require_roles(Role.ADMIN))])
def update_product(product_id: str, payload: ProductUpdateIn, db: Session = Depends(get_db)) -> ProductOut:
    product = db.scalar(
        select(ProductModel).options(joinedload(ProductModel.category)).where(ProductModel.id == product_id)
    )
    if product is None:
        raise ProductNotFoundError(product_id)

    changes = payload.model_dump(exclude_unset=True)
    _validate_image_key(changes.get("image_key"))
    if changes.get("category_id") and db.get(ProductCategoryModel, changes["category_id"]) is None:
        raise ProductCategoryNotFoundError(changes["category_id"])
    previous_image_key = product.image_key
    for field, value in changes.items():
        setattr(product, field, value)
    _commit(db)
    db.refresh(product)
    if previous_image_key != product.image_key:
        _delete_image_best_effort(previous_image_key)
    return _out(product)


@router.post(
    "/images",
    response_model=ProductImageUploadOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(Role.ADMIN))],
)
def upload_product_image(file: UploadFile = File(...)) -> ProductImageUploadOut:
    content_type = file.content_type or ""
    contents = file.file.read(MAX_PRODUCT_IMAGE_BYTES + 1)
    storage = MinioProductImageStorage()
    image_key = storage.upload(contents, content_type)
    return ProductImageUploadOut(image_key=image_key, image_url=f"/api/v1/products/images/{image_key}")


@router.get("/images/{image_key:path}", response_model=None)
def get_product_image(image_key: str) -> Response:
    _validate_image_key(image_key)
    contents, content_type = MinioProductImageStorage().read(image_key)
    if len(contents) > MAX_PRODUCT_IMAGE_BYTES:
        raise InvalidProductImageError()
    return Response(
        content=contents,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.delete(
    "/images",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(Role.ADMIN))],
)
def delete_product_image(image_key: str = Query(min_length=9, max_length=512)) -> Response:
    _validate_image_key(image_key)
    MinioProductImageStorage().delete(image_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles(Role.ADMIN))])
def delete_product(product_id: str, db: Session = Depends(get_db)) -> Response:
    product = db.get(ProductModel, product_id)
    if product is None:
        raise ProductNotFoundError(product_id)
    image_key = product.image_key
    db.delete(product)
    db.commit()
    _delete_image_best_effort(image_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

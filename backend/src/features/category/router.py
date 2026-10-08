"""Lecture publique du catalogue et CRUD des catégories réservé aux administrateurs."""

import re
import unicodedata

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.errors import DomainError
from src.domain.user import Role
from src.features.category.schemas import CategoryCreateIn, CategoryOut, CategoryUpdateIn
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.models import ProductCategoryModel
from src.infrastructure.security.deps import require_roles

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryNotFoundError(DomainError):
    def __init__(self, category_id: str) -> None:
        super().__init__(f"Category '{category_id}' not found")


class CategoryAlreadyExistsError(DomainError):
    def __init__(self) -> None:
        super().__init__("A category with this slug already exists")


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:140].strip("-")


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise CategoryAlreadyExistsError() from exc


@router.get("", response_model=list[CategoryOut])
def list_active_categories(db: Session = Depends(get_db)) -> list[ProductCategoryModel]:
    return list(db.scalars(select(ProductCategoryModel).where(ProductCategoryModel.is_active.is_(True)).order_by(ProductCategoryModel.name)))


@router.get("/manage", response_model=list[CategoryOut], dependencies=[Depends(require_roles(Role.ADMIN))])
def list_categories_for_admin(db: Session = Depends(get_db)) -> list[ProductCategoryModel]:
    return list(db.scalars(select(ProductCategoryModel).order_by(ProductCategoryModel.name)))


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles(Role.ADMIN))])
def create_category(payload: CategoryCreateIn, db: Session = Depends(get_db)) -> ProductCategoryModel:
    slug = _slugify(payload.slug or payload.name)
    if not slug:
        raise CategoryAlreadyExistsError()
    category = ProductCategoryModel(
        name=payload.name.strip(),
        slug=slug,
        description=payload.description.strip(),
        is_active=payload.is_active,
    )
    db.add(category)
    _commit(db)
    db.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryOut, dependencies=[Depends(require_roles(Role.ADMIN))])
def update_category(
    category_id: str, payload: CategoryUpdateIn, db: Session = Depends(get_db)
) -> ProductCategoryModel:
    category = db.get(ProductCategoryModel, category_id)
    if category is None:
        raise CategoryNotFoundError(category_id)

    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        changes["name"] = changes["name"].strip()
    if "description" in changes and changes["description"] is not None:
        changes["description"] = changes["description"].strip()
    if "slug" in changes:
        changes["slug"] = _slugify(changes["slug"] or changes.get("name") or category.name)
        if not changes["slug"]:
            raise CategoryAlreadyExistsError()
    for field, value in changes.items():
        setattr(category, field, value)

    _commit(db)
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles(Role.ADMIN))])
def delete_category(category_id: str, db: Session = Depends(get_db)) -> Response:
    category = db.get(ProductCategoryModel, category_id)
    if category is None:
        raise CategoryNotFoundError(category_id)
    db.delete(category)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

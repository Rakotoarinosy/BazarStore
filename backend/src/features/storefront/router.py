"""Images et visuels configurables de la boutique."""

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from src.domain.user import Role
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.models import StorefrontSettingsModel
from src.infrastructure.security.deps import require_roles
from src.infrastructure.storage.minio_product_images import (
    MAX_PRODUCT_IMAGE_BYTES,
    MinioProductImageStorage,
)

router = APIRouter(prefix="/storefront", tags=["storefront"])


def _settings_out(settings: StorefrontSettingsModel) -> dict[str, str | None]:
    return {
        "hero_main_image_key": settings.hero_main_image_key,
        "hero_main_image_url": _image_url(settings.hero_main_image_key),
        "hero_secondary_image_key": settings.hero_secondary_image_key,
        "hero_secondary_image_url": _image_url(settings.hero_secondary_image_key),
    }


def _image_url(image_key: str | None) -> str | None:
    return f"/api/v1/storefront/images/{image_key}" if image_key else None


@router.get("/settings")
def get_storefront_settings(db: Session = Depends(get_db)) -> dict[str, str | None]:
    settings = db.get(StorefrontSettingsModel, "default")
    if settings is None:
        settings = StorefrontSettingsModel(id="default")
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return _settings_out(settings)


@router.patch("/settings", dependencies=[Depends(require_roles(Role.ADMIN))])
def update_storefront_settings(
    payload: dict[str, str | None], db: Session = Depends(get_db)
) -> dict[str, str | None]:
    allowed = {"hero_main_image_key", "hero_secondary_image_key"}
    if not payload or set(payload) - allowed:
        raise HTTPException(status_code=422, detail="Invalid storefront settings fields")
    for key in payload.values():
        if key is not None and (not key.startswith("storefront/") or ".." in key):
            raise HTTPException(status_code=422, detail="Invalid storefront image key")
    settings = db.get(StorefrontSettingsModel, "default")
    if settings is None:
        settings = StorefrontSettingsModel(id="default")
        db.add(settings)
    for field, value in payload.items():
        setattr(settings, field, value)
    db.commit()
    db.refresh(settings)
    return _settings_out(settings)


@router.post(
    "/images",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(Role.ADMIN))],
)
def upload_storefront_image(
    file: UploadFile = File(...), kind: str = Query(default="storefront", pattern="^(storefront|categories)$")
) -> dict[str, str]:
    contents = file.file.read(MAX_PRODUCT_IMAGE_BYTES + 1)
    image_key = MinioProductImageStorage().upload(contents, file.content_type or "", kind)
    return {"image_key": image_key, "image_url": f"/api/v1/storefront/images/{image_key}"}


@router.get("/images/{image_key:path}", response_model=None)
def get_storefront_image(image_key: str) -> Response:
    if not (image_key.startswith("storefront/") or image_key.startswith("categories/")) or ".." in image_key:
        from src.infrastructure.storage.minio_product_images import InvalidProductImageError

        raise InvalidProductImageError("Invalid storefront image key")
    contents, content_type = MinioProductImageStorage().read(image_key)
    if len(contents) > MAX_PRODUCT_IMAGE_BYTES:
        from src.infrastructure.storage.minio_product_images import InvalidProductImageError

        raise InvalidProductImageError()
    return Response(content=contents, media_type=content_type, headers={"Cache-Control": "public, max-age=3600"})

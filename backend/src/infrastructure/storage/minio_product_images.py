"""Stockage privé MinIO des images du catalogue BazarStore."""

from __future__ import annotations

from io import BytesIO
from urllib.parse import urlparse
from uuid import uuid4

from minio import Minio
from minio.error import S3Error

from src.domain.errors import DomainError
from src.infrastructure.config import get_settings

MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024
_IMAGE_FORMATS: tuple[tuple[str, str, bytes], ...] = (
    ("image/jpeg", "jpg", b"\xff\xd8\xff"),
    ("image/png", "png", b"\x89PNG\r\n\x1a\n"),
    ("image/gif", "gif", b"GIF8"),
)


class ProductImageStorageUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__("Product image storage is not configured or unavailable")


class InvalidProductImageError(DomainError):
    def __init__(self, message: str = "Use a JPEG, PNG, GIF, or WebP image up to 5 MB") -> None:
        super().__init__(message)


class MinioProductImageStorage:
    def __init__(self) -> None:
        self.settings = get_settings()

    def upload(self, contents: bytes, content_type: str, namespace: str = "products") -> str:
        normalized_type = content_type.lower().split(";", maxsplit=1)[0].strip()
        extension = self._extension_for(contents, normalized_type)
        client = self._client()
        try:
            if not client.bucket_exists(self.settings.minio_bucket):
                client.make_bucket(self.settings.minio_bucket)
            object_name = f"{namespace}/{uuid4().hex}.{extension}"
            client.put_object(
                self.settings.minio_bucket,
                object_name,
                BytesIO(contents),
                length=len(contents),
                content_type=normalized_type,
            )
            return object_name
        except Exception as exc:
            raise ProductImageStorageUnavailableError() from exc

    def read(self, object_name: str) -> tuple[bytes, str]:
        response = None
        try:
            response = self._client().get_object(self.settings.minio_bucket, object_name)
            return response.read(MAX_PRODUCT_IMAGE_BYTES + 1), response.headers.get("Content-Type", "application/octet-stream")
        except Exception as exc:
            raise ProductImageStorageUnavailableError() from exc
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def delete(self, object_name: str) -> None:
        try:
            self._client().remove_object(self.settings.minio_bucket, object_name)
        except Exception as exc:
            raise ProductImageStorageUnavailableError() from exc

    def _client(self) -> Minio:
        settings = self.settings
        if not settings.minio_access_key or not settings.minio_secret_key:
            raise ProductImageStorageUnavailableError()
        parsed = urlparse(settings.minio_endpoint if "://" in settings.minio_endpoint else f"//{settings.minio_endpoint}")
        endpoint = parsed.netloc or parsed.path
        if not endpoint:
            raise ProductImageStorageUnavailableError()
        secure = settings.minio_secure or parsed.scheme == "https"
        return Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=secure,
        )

    @staticmethod
    def _extension_for(contents: bytes, content_type: str) -> str:
        if not contents or len(contents) > MAX_PRODUCT_IMAGE_BYTES:
            raise InvalidProductImageError()
        if content_type == "image/webp" and len(contents) >= 12 and contents[:4] == b"RIFF" and contents[8:12] == b"WEBP":
            return "webp"
        for allowed_type, extension, signature in _IMAGE_FORMATS:
            if content_type == allowed_type and contents.startswith(signature):
                return extension
        raise InvalidProductImageError()

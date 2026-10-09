"""Configuration de l'application, chargée depuis les variables d'environnement et `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/.env, quel que soit le dossier de lancement (uvicorn, Passenger, pytest…).
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

DEFAULT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "production", "test"] = "development"
    database_url: str = "sqlite:///./app.db"
    # NoDecode : la valeur est une liste séparée par des virgules, pas du JSON.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:4200"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    secret_key: str = DEFAULT_SECRET
    # Fuseau de la municipalité : définit ce qu'est « aujourd'hui » dans le dashboard.
    app_timezone: str = "Indian/Antananarivo"

    # ─── Auth ───
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    max_failed_login_attempts: int = 5
    lockout_minutes: int = 15
    # Cookie du refresh token. "none" uniquement si front et API sont sur des sites différents.
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # Premier administrateur, créé au démarrage s'il n'existe aucun admin actif.
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_name: str = "Administrateur"

    # OAuth Google : l'identifiant client est public, mais reste configurable par environnement.
    google_client_id: str | None = None
    # Flux OAuth côté serveur (connexion depuis Scalar) : secret jamais exposé au client.
    google_client_secret: str | None = None

    # MinIO/S3 : les images sont servies par l'API BazarStore sur la même origine que le frontend.
    minio_endpoint: str = "127.0.0.1:9010"
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_bucket: str = "bazarstore-products"
    minio_secure: bool = False

    # ─── IA (analyse des demandes) ───
    # Sans clé, POST /requests/{id}/analyze répond 503 ; le reste de l'API fonctionne normalement.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def uppercase_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def reject_weak_secret_in_production(self) -> "Settings":
        if self.environment == "production" and (
            self.secret_key == DEFAULT_SECRET or len(self.secret_key) < 32
        ):
            raise ValueError(
                "SECRET_KEY must be a random string of at least 32 characters in production"
            )
        if self.environment == "production" and "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must not contain '*' (credentials are enabled)")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cookie_secure(self) -> bool:
        return self.is_production or self.cookie_samesite == "none"


@lru_cache
def get_settings() -> Settings:
    """Instance unique des settings (mise en cache après la première lecture)."""
    return Settings()

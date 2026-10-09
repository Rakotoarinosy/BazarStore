"""Création du premier administrateur au démarrage (si aucun admin actif n'existe).

Renseigner BOOTSTRAP_ADMIN_EMAIL et BOOTSTRAP_ADMIN_PASSWORD dans .env, démarrer une fois,
puis RETIRER le mot de passe du .env.
"""

import logging

from src.domain.user import Role, UserConflictError
from src.features.user.schemas import CreateUserIn
from src.features.user.use_cases import create_user
from src.infrastructure.config import get_settings
from src.infrastructure.persistence.database import SessionLocal
from src.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from src.infrastructure.security.password import Argon2PasswordHasher

logger = logging.getLogger(__name__)


def ensure_bootstrap_admin() -> None:
    settings = get_settings()
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return

    try:
        with SessionLocal() as db:
            repo = SqlAlchemyUserRepository(db)
            if repo.count_active_by_role(Role.ADMIN) > 0:
                return

            dto = CreateUserIn(
                email=settings.bootstrap_admin_email,
                name=settings.bootstrap_admin_name,
                password=settings.bootstrap_admin_password,
                role=Role.ADMIN,
            )
            create_user(dto, repo, Argon2PasswordHasher())
            logger.info("bootstrap admin created", extra={"email": dto.email})
    except UserConflictError:
        # Plusieurs workers uvicorn démarrent en même temps : un autre l'a créé à l'instant.
        logger.info("bootstrap admin already created by another worker")
    except Exception:
        # Ne bloque pas le démarrage (ex. migrations pas encore appliquées, mot de passe trop faible).
        logger.exception("bootstrap admin failed")

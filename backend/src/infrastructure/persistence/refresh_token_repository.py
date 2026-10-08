"""Implémentation SQLAlchemy de RefreshTokenRepository."""

from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from src.domain.user.entities import RefreshToken
from src.domain.user.repository import RefreshTokenRepository
from src.infrastructure.persistence.models import RefreshTokenModel


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=value.tzinfo or UTC)


class SqlAlchemyRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, token: RefreshToken) -> RefreshToken:
        self.db.add(
            RefreshTokenModel(
                id=token.id,
                user_id=token.user_id,
                family_id=token.family_id,
                token_hash=token.token_hash,
                expires_at=token.expires_at,
                created_at=token.created_at,
                revoked_at=token.revoked_at,
            )
        )
        self.db.commit()

        return token

    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        model = self.db.scalar(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
        if model is None:
            return None

        return RefreshToken(
            id=model.id,
            user_id=model.user_id,
            family_id=model.family_id,
            token_hash=model.token_hash,
            expires_at=_aware(model.expires_at),
            created_at=_aware(model.created_at),
            revoked_at=_aware(model.revoked_at) if model.revoked_at else None,
        )

    def revoke(self, token_id: str, now: datetime) -> bool:
        # Atomique : un seul appel concurrent peut passer de « actif » à « révoqué ».
        result = self.db.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.id == token_id, RefreshTokenModel.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        self.db.commit()

        return result.rowcount > 0

    def revoke_family(self, family_id: str, now: datetime) -> None:
        self.db.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.family_id == family_id, RefreshTokenModel.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        self.db.commit()

    def revoke_all_for_user(self, user_id: str, now: datetime) -> None:
        self.db.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.user_id == user_id, RefreshTokenModel.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        self.db.commit()

    def delete_expired(self, now: datetime) -> None:
        self.db.execute(delete(RefreshTokenModel).where(RefreshTokenModel.expires_at < now))
        self.db.commit()

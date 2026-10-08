"""Implémentation SQLAlchemy de UserRepository. Le mapping Model ↔ Entity reste privé à ce fichier."""

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.user.entities import Role, User
from src.domain.user.exceptions import UserConflictError
from src.domain.user.repository import UserRepository
from src.infrastructure.persistence.models import RefreshTokenModel, UserModel


def _aware(value: datetime | None) -> datetime | None:
    # SQLite ne conserve pas le fuseau : on garantit un datetime UTC « aware » partout.
    return value.replace(tzinfo=value.tzinfo or UTC) if value else None


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: str) -> User | None:
        model = self.db.get(UserModel, user_id)

        return self._to_entity(model) if model else None

    def get_by_email(self, email: str) -> User | None:
        model = self.db.scalar(select(UserModel).where(UserModel.email == email))

        return self._to_entity(model) if model else None

    def count_active_by_role(self, role: Role) -> int:
        stmt = (
            select(func.count())
            .select_from(UserModel)
            .where(UserModel.role == role.value, UserModel.is_active.is_(True))
        )

        return self.db.scalar(stmt) or 0

    def add(self, user: User) -> User:
        model = self._to_model(user)
        self.db.add(model)
        self._commit()

        return self._to_entity(model)

    def update(self, user: User) -> User:
        model = self.db.merge(self._to_model(user))
        self._commit()

        return self._to_entity(model)

    def delete(self, user_id: str) -> None:
        # Nettoyage explicite : SQLite n'applique pas ON DELETE CASCADE par défaut.
        self.db.execute(delete(RefreshTokenModel).where(RefreshTokenModel.user_id == user_id))
        model = self.db.get(UserModel, user_id)
        if model:
            self.db.delete(model)
        self.db.commit()

    def list(self) -> list[User]:
        models = self.db.scalars(select(UserModel).order_by(UserModel.created_at))

        return [self._to_entity(model) for model in models]

    # ─── Interne ────────────────────────────────────────────────────

    def _commit(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise UserConflictError() from exc

    def _to_entity(self, model: UserModel) -> User:
        return User(
            id=model.id,
            email=model.email,
            name=model.name,
            created_at=_aware(model.created_at),  # type: ignore[arg-type]
            password_hash=model.password_hash,
            role=Role(model.role),
            is_active=model.is_active,
            agent_id=model.agent_id,
            google_subject=model.google_subject,
            failed_login_attempts=model.failed_login_attempts,
            locked_until=_aware(model.locked_until),
        )

    def _to_model(self, user: User) -> UserModel:
        return UserModel(
            id=user.id,
            email=user.email,
            name=user.name,
            password_hash=user.password_hash,
            role=user.role.value,
            is_active=user.is_active,
            agent_id=user.agent_id,
            google_subject=user.google_subject,
            failed_login_attempts=user.failed_login_attempts,
            locked_until=user.locked_until,
            created_at=user.created_at,
        )

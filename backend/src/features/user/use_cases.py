"""Use cases de gestion des utilisateurs (ADMIN). Ne dépendent que du domaine et des schémas."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime

from src.domain.user import (
    LastAdminError,
    PasswordHasher,
    RefreshTokenRepository,
    Role,
    User,
    UserAlreadyExistsError,
    UserNotFoundError,
    UserRepository,
)
from src.features.user.schemas import CreateUserIn, UpdateUserIn


def create_user(dto: CreateUserIn, repo: UserRepository, hasher: PasswordHasher) -> User:
    if repo.get_by_email(dto.email):
        raise UserAlreadyExistsError(dto.email)

    user = User(
        id=str(uuid.uuid4()),
        email=dto.email,
        name=dto.name,
        created_at=datetime.now(UTC),
        password_hash=hasher.hash(dto.password),
        role=dto.role,
        agent_id=dto.agent_id,
    )

    return repo.add(user)


def get_user(user_id: str, repo: UserRepository) -> User:
    user = repo.get_by_id(user_id)
    if user is None:
        raise UserNotFoundError(user_id)

    return user


def list_users(repo: UserRepository) -> list[User]:
    return repo.list()


def update_user(
    user_id: str,
    dto: UpdateUserIn,
    repo: UserRepository,
    refresh_repo: RefreshTokenRepository,
    hasher: PasswordHasher,
) -> User:
    user = get_user(user_id, repo)
    changes = dto.model_dump(exclude_unset=True)

    # Seul agent_id accepte un null explicite ; ailleurs, null signifie « ne pas toucher ».
    for field in ("email", "name", "role", "is_active", "password"):
        if changes.get(field) is None:
            changes.pop(field, None)

    new_email = changes.get("email")
    if new_email and new_email != user.email and repo.get_by_email(new_email):
        raise UserAlreadyExistsError(new_email)

    new_role = changes.get("role", user.role)
    new_active = changes.get("is_active", user.is_active)
    _ensure_admin_remains(user, new_role, new_active, repo)

    password = changes.pop("password", None)
    if password:
        changes["password_hash"] = hasher.hash(password)

    # Toute modification sensible force une reconnexion sur tous les appareils.
    sensitive = {"role", "is_active", "password_hash", "email"} & changes.keys()
    updated = repo.update(replace(user, **changes))
    if sensitive:
        refresh_repo.revoke_all_for_user(user.id, datetime.now(UTC))

    return updated


def delete_user(user_id: str, repo: UserRepository) -> None:
    user = get_user(user_id, repo)
    _ensure_admin_remains(user, new_role=Role.CITIZEN, new_active=False, repo=repo)
    repo.delete(user_id)


def _ensure_admin_remains(user: User, new_role: Role, new_active: bool, repo: UserRepository) -> None:
    """Empêche de supprimer, rétrograder ou désactiver le dernier admin actif."""
    loses_admin = user.role is Role.ADMIN and user.is_active and (new_role is not Role.ADMIN or not new_active)
    if loses_admin and repo.count_active_by_role(Role.ADMIN) <= 1:
        raise LastAdminError()

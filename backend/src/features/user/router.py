"""Endpoints HTTP de gestion des utilisateurs : réservés à l'ADMIN (dépendance au niveau du router).

Un changement de rôle est un simple PATCH /users/{id} {"role": "manager"} ; il prend effet
immédiatement (le rôle est relu en base à chaque requête) et déconnecte l'utilisateur.
"""

from fastapi import APIRouter, Depends, status

from src.domain.user import PasswordHasher, RefreshTokenRepository, Role, User, UserRepository
from src.features.user.schemas import CreateUserIn, UpdateUserIn, UserOut
from src.features.user.use_cases import (
    create_user,
    delete_user,
    get_user,
    list_users,
    update_user,
)
from src.infrastructure.security.deps import (
    get_password_hasher,
    get_refresh_token_repo,
    get_user_repo,
    require_roles,
)

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_roles(Role.ADMIN))],
)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user_endpoint(
    payload: CreateUserIn,
    repo: UserRepository = Depends(get_user_repo),
    hasher: PasswordHasher = Depends(get_password_hasher),
) -> User:
    return create_user(payload, repo, hasher)


@router.get("", response_model=list[UserOut])
def list_users_endpoint(repo: UserRepository = Depends(get_user_repo)) -> list[User]:
    return list_users(repo)


@router.get("/{user_id}", response_model=UserOut)
def get_user_endpoint(user_id: str, repo: UserRepository = Depends(get_user_repo)) -> User:
    return get_user(user_id, repo)


@router.patch("/{user_id}", response_model=UserOut)
def update_user_endpoint(
    user_id: str,
    payload: UpdateUserIn,
    repo: UserRepository = Depends(get_user_repo),
    refresh_repo: RefreshTokenRepository = Depends(get_refresh_token_repo),
    hasher: PasswordHasher = Depends(get_password_hasher),
) -> User:
    return update_user(user_id, payload, repo, refresh_repo, hasher)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_endpoint(user_id: str, repo: UserRepository = Depends(get_user_repo)) -> None:
    delete_user(user_id, repo)

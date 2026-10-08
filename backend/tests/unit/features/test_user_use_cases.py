import pytest

from src.domain.user import User, UserAlreadyExistsError, UserNotFoundError
from src.features.user.schemas import CreateUserIn, UpdateUserIn
from src.features.user.use_cases import (
    create_user,
    delete_user,
    get_user,
    list_users,
    update_user,
)
from tests.fakes import FakeUserRepository


@pytest.fixture
def repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def ada(repo: FakeUserRepository) -> User:
    return create_user(CreateUserIn(email="ada@example.com", name="Ada"), repo)


def test_get_user_raises_when_missing(repo: FakeUserRepository) -> None:
    with pytest.raises(UserNotFoundError):
        get_user("missing", repo)


def test_list_users(repo: FakeUserRepository, ada: User) -> None:
    assert list_users(repo) == [ada]


def test_update_user_changes_only_given_fields(repo: FakeUserRepository, ada: User) -> None:
    updated = update_user(ada.id, UpdateUserIn(name="Ada Lovelace"), repo)

    assert updated.name == "Ada Lovelace"
    assert updated.email == ada.email
    assert updated.created_at == ada.created_at


def test_update_user_rejects_an_email_already_taken(repo: FakeUserRepository, ada: User) -> None:
    create_user(CreateUserIn(email="grace@example.com", name="Grace"), repo)

    with pytest.raises(UserAlreadyExistsError):
        update_user(ada.id, UpdateUserIn(email="grace@example.com"), repo)


def test_update_user_accepts_its_own_email(repo: FakeUserRepository, ada: User) -> None:
    updated = update_user(ada.id, UpdateUserIn(email="ada@example.com", name="A"), repo)

    assert updated.name == "A"


def test_delete_user(repo: FakeUserRepository, ada: User) -> None:
    delete_user(ada.id, repo)

    assert repo.get_by_id(ada.id) is None


def test_delete_user_raises_when_missing(repo: FakeUserRepository) -> None:
    with pytest.raises(UserNotFoundError):
        delete_user("missing", repo)

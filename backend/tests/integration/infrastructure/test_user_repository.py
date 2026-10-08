from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.domain.user import User
from src.infrastructure.persistence.user_repository import SqlAlchemyUserRepository


def make_user(user_id: str = "u1", email: str = "ada@example.com") -> User:
    return User(id=user_id, email=email, name="Ada", created_at=datetime.now(UTC))


def test_add_then_get_by_id_and_email(db_session: Session) -> None:
    repo = SqlAlchemyUserRepository(db_session)
    user = repo.add(make_user())

    assert repo.get_by_id(user.id) == user
    assert repo.get_by_email("ada@example.com") == user
    assert repo.get_by_id("missing") is None


def test_created_at_is_timezone_aware(db_session: Session) -> None:
    repo = SqlAlchemyUserRepository(db_session)
    repo.add(make_user())
    db_session.expire_all()  # force la relecture depuis SQLite, qui perd le fuseau

    user = repo.get_by_id("u1")

    assert user is not None
    assert user.created_at.tzinfo is not None


def test_list_update_delete(db_session: Session) -> None:
    repo = SqlAlchemyUserRepository(db_session)
    repo.add(make_user("u1", "a@example.com"))
    repo.add(make_user("u2", "b@example.com"))

    assert [u.id for u in repo.list()] == ["u1", "u2"]

    user = repo.get_by_id("u1")
    assert user is not None
    user.name = "Ada Lovelace"
    repo.update(user)
    assert repo.get_by_id("u1") == user

    repo.delete("u1")
    assert repo.get_by_id("u1") is None
    repo.delete("u1")  # supprimer un absent ne lève pas d'erreur

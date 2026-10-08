"""Repositories en mémoire pour les tests unitaires : ni base de données, ni HTTP."""

from src.domain.user import User, UserRepository


class FakeUserRepository(UserRepository):
    def __init__(self) -> None:
        self.users: dict[str, User] = {}

    def get_by_id(self, user_id: str) -> User | None:
        return self.users.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        return next((user for user in self.users.values() if user.email == email), None)

    def list(self) -> list[User]:
        return list(self.users.values())

    def add(self, user: User) -> User:
        self.users[user.id] = user
        return user

    def update(self, user: User) -> User:
        self.users[user.id] = user
        return user

    def delete(self, user_id: str) -> None:
        self.users.pop(user_id, None)
